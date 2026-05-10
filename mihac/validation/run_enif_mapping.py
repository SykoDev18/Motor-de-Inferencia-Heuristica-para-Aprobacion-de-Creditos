# ============================================================
# MIHAC v2.0 — Orquestador del mapeo ENIF 2024 → InferenceEngine
# validation/run_enif_mapping.py
# ============================================================
# Carga las tablas completas de ENIF 2024, las pasa por
# data/mapper_enif.py, evalúa cada fila con InferenceEngine y
# persiste tres entregables:
#
#   reports/enif_mapped.csv       — 13,502 filas con las 9
#                                   variables MIHAC + flags
#                                   de auditoría.
#   reports/enif_evaluations.csv  — dictamen + score + reglas
#                                   activadas por fila.
#   reports/mapping_stats.md      — resumen ejecutivo del
#                                   mapeo (cobertura, dictá-
#                                   menes, comparación CNBV).
#
# Uso (desde la raíz del proyecto mihac/):
#
#   ../.venv/Scripts/python.exe -X utf8 validation/run_enif_mapping.py
#
# Tiempo esperado: ~10 segundos sobre 13,502 filas.
# ============================================================

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import pandas as pd

_VALID_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _VALID_DIR.parent
_REPORTS_DIR = _PROJECT_ROOT / "reports"

# Permitir imports desde la raíz del proyecto
sys.path.insert(0, str(_PROJECT_ROOT))

from core.engine import InferenceEngine  # noqa: E402
from data.mapper_enif import (  # noqa: E402
    load_enif_tables,
    map_enif_to_mihac,
    to_mihac_dict,
)

logger = logging.getLogger(__name__)


# ── Métricas de referencia CNBV (microcréditos, feb-2024) ────

_IMOR_MICROCREDITOS_MX = 0.035   # Tasa de mora real
_IMOR_PERSONALES_MX = 0.049      # Tasa de mora créditos personales


# ── Helpers ──────────────────────────────────────────────────

def _evaluate_all(
    mapped: pd.DataFrame, engine: InferenceEngine
) -> pd.DataFrame:
    """Corre engine.evaluate() sobre cada fila mapeada.

    Returns:
        DataFrame con columnas:
            llavemod, dictamen, score_final, dti_ratio,
            dti_clasificacion, reglas_activadas, n_reglas,
            n_compensaciones, errores_validacion.
    """
    registros: list[dict] = []
    excepciones = 0

    for _, fila in mapped.iterrows():
        datos = to_mihac_dict(fila)
        try:
            res = engine.evaluate(datos)
        except Exception as e:  # pragma: no cover (defensive)
            excepciones += 1
            registros.append(
                {
                    "llavemod": int(fila["llavemod"]),
                    "dictamen": "ERROR",
                    "score_final": 0,
                    "dti_ratio": 0.0,
                    "dti_clasificacion": "N/A",
                    "reglas_activadas": "",
                    "n_reglas": 0,
                    "n_compensaciones": 0,
                    "errores_validacion": str(e),
                }
            )
            continue

        reglas = res.get("reglas_activadas", [])
        compensaciones = res.get("compensaciones", [])
        ids = "|".join(r["id"] for r in reglas)
        errs = "|".join(res.get("errores_validacion", []) or [])

        registros.append(
            {
                "llavemod": int(fila["llavemod"]),
                "dictamen": res["dictamen"],
                "score_final": res["score_final"],
                "dti_ratio": res["dti_ratio"],
                "dti_clasificacion": res["dti_clasificacion"],
                "reglas_activadas": ids,
                "n_reglas": len(reglas),
                "n_compensaciones": len(compensaciones),
                "errores_validacion": errs,
            }
        )

    if excepciones:
        logger.warning(
            "Se produjeron %d excepciones durante la "
            "evaluación (registradas como ERROR)",
            excepciones,
        )

    return pd.DataFrame(registros)


def _build_stats_md(
    mapped: pd.DataFrame,
    evaluations: pd.DataFrame,
    elapsed: float,
) -> str:
    """Construye el reporte Markdown con estadísticas globales."""
    n = len(mapped)
    n_imp_ingreso = int(mapped["ingreso_imputado"].sum())

    dist_dictamen = (
        evaluations["dictamen"].value_counts().to_dict()
    )
    aprob = dist_dictamen.get("APROBADO", 0)
    rev = dist_dictamen.get("REVISION_MANUAL", 0)
    rech = dist_dictamen.get("RECHAZADO", 0)
    err = dist_dictamen.get("ERROR", 0)
    tasa_aprob = aprob / n * 100 if n else 0.0
    tasa_rech = rech / n * 100 if n else 0.0

    # Reglas más activadas (split por '|')
    todas_reglas = (
        evaluations["reglas_activadas"]
        .dropna()
        .str.split("|")
        .explode()
    )
    todas_reglas = todas_reglas[todas_reglas != ""]
    top_reglas = todas_reglas.value_counts().head(15).to_dict()

    # Distribuciones derivadas
    dist_hist = mapped["historial_crediticio"].value_counts().sort_index().to_dict()
    dist_viv = mapped["tipo_vivienda"].value_counts().to_dict()
    dist_prop = mapped["proposito_credito"].value_counts().to_dict()
    dist_antig = mapped["antiguedad_laboral"].value_counts().sort_index().to_dict()
    dist_dti = evaluations["dti_clasificacion"].value_counts().to_dict()

    # Estadísticas numéricas
    ing_min = mapped["ingreso_mensual"].min()
    ing_med = mapped["ingreso_mensual"].median()
    ing_max = mapped["ingreso_mensual"].max()
    ing_mean = mapped["ingreso_mensual"].mean()
    score_min = evaluations["score_final"].min()
    score_med = evaluations["score_final"].median()
    score_max = evaluations["score_final"].max()
    score_mean = evaluations["score_final"].mean()

    # Comparación con IMOR CNBV
    pct_malo = dist_hist.get(0, 0) / n * 100

    lines: list[str] = []
    lines.append("# Mapeo ENIF 2024 → MIHAC — Reporte de ejecución\n")
    lines.append(
        "**Generado:** "
        f"{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}  \n"
    )
    lines.append(
        f"**Tiempo de ejecución:** {elapsed:.2f} s  \n"
    )
    lines.append(f"**Filas procesadas:** {n:,}  \n\n")

    lines.append("## 1. Cobertura del mapeo\n\n")
    lines.append("| Métrica | Valor |\n|---|---:|\n")
    lines.append(
        f"| Filas mapeadas | {n:,} |\n"
        f"| Ingreso imputado (mediana × niv) | "
        f"{n_imp_ingreso:,} ({n_imp_ingreso/n*100:.1f}%) |\n"
        f"| Deuda imputada (DTI=0.30 sintético) | "
        f"{n:,} (100.0%) |\n"
        f"| Excepciones del engine | {err} |\n\n"
    )

    lines.append("## 2. Distribución de dictámenes\n\n")
    lines.append("| Dictamen | Filas | Porcentaje |\n|---|---:|---:|\n")
    for d in ("APROBADO", "REVISION_MANUAL", "RECHAZADO", "ERROR"):
        c = dist_dictamen.get(d, 0)
        lines.append(f"| {d} | {c:,} | {c/n*100:.2f}% |\n")
    lines.append("\n")

    lines.append("## 3. Distribución de DTI sintético\n\n")
    lines.append(
        "Por construcción, todas las filas deberían quedar en "
        "DTI=0.30 (MODERADO). Si aparecen otras clases, indica "
        "filas con ingreso muy bajo o errores numéricos.\n\n"
    )
    lines.append("| Clasificación | Filas |\n|---|---:|\n")
    for k, v in dist_dti.items():
        lines.append(f"| {k} | {v:,} |\n")
    lines.append("\n")

    lines.append("## 4. Estadísticas numéricas\n\n")
    lines.append("| Variable | Min | Mediana | Media | Max |\n|---|---:|---:|---:|---:|\n")
    lines.append(
        f"| ingreso_mensual | ${ing_min:,.0f} | ${ing_med:,.0f} "
        f"| ${ing_mean:,.0f} | ${ing_max:,.0f} |\n"
    )
    lines.append(
        f"| score_final | {score_min} | {score_med:.0f} "
        f"| {score_mean:.1f} | {score_max} |\n\n"
    )

    lines.append("## 5. Distribuciones categóricas (mapeadas)\n\n")
    lines.append(f"- **historial_crediticio** (0=Malo, 1=Neutro, 2=Bueno): `{dist_hist}`\n")
    lines.append(f"- **tipo_vivienda**: `{dist_viv}`\n")
    lines.append(f"- **proposito_credito**: `{dist_prop}`\n")
    lines.append(f"- **antiguedad_laboral** (años): `{dist_antig}`\n\n")

    lines.append("## 6. Top reglas heurísticas activadas\n\n")
    lines.append("| Regla | Activaciones | % de filas |\n|---|---:|---:|\n")
    for rid, cnt in top_reglas.items():
        lines.append(f"| {rid} | {cnt:,} | {cnt/n*100:.1f}% |\n")
    lines.append("\n")

    lines.append("## 7. Comparación con tasas de mora CNBV (feb-2024)\n\n")
    lines.append(
        "| Indicador | Valor MIHAC sobre ENIF | Referencia CNBV |\n"
        "|---|---:|---:|\n"
        f"| Tasa de rechazo del motor | {tasa_rech:.2f}% | n/a |\n"
        f"| Tasa de aprobación del motor | {tasa_aprob:.2f}% | n/a |\n"
        f"| % historial Malo (derivado) | {pct_malo:.2f}% | "
        f"IMOR microcréditos = "
        f"{_IMOR_MICROCREDITOS_MX*100:.1f}% |\n"
        f"| | | IMOR personales = "
        f"{_IMOR_PERSONALES_MX*100:.1f}% |\n\n"
        "**Lectura:** la tasa de rechazo del motor refleja el "
        "perfil socioeconómico capturado por ENIF (bajos "
        "ingresos, alta proporción sin antigüedad formal). No "
        "es directamente comparable con IMOR — IMOR mide mora "
        "*ex post* sobre cartera colocada, mientras que MIHAC "
        "evalúa solicitudes hipotéticas con un monto fijo "
        "asignado por propósito.\n\n"
    )

    lines.append("## 8. Limitaciones de este mapeo\n\n")
    lines.append(
        "- ENIF no captura el monto absoluto de deuda; usamos "
        "DTI sintético = 0.30. Esto neutraliza R011, R013, "
        "R014 y el veto DTI por diseño.\n"
        "- ENIF no captura monto del crédito solicitado; "
        "usamos medianas CNBV por propósito.\n"
        "- ENIF no captura antigüedad laboral exacta; "
        "derivamos de p3_10 × p3_13.\n"
        "- tipo_vivienda colapsa Rentada/Prestada en "
        "'Familiar' (ENIF solo distingue propietario sí/no "
        "vía p13_2_1).\n"
        "- proposito_credito es una traducción gruesa del "
        "tipo de crédito tenido (p6_2_x); no refleja la "
        "intención de uso de un crédito hipotético nuevo.\n"
    )

    return "".join(lines)


# ── Main ─────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-25s | %(message)s",
    )
    print("=" * 70)
    print("MIHAC v2.0 — Orquestador del mapeo ENIF 2024 (full run)")
    print("=" * 70)

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()

    # 1) Cargar ENIF
    tmod, tsd = load_enif_tables()
    print(
        f"\nTablas cargadas — tmodulo: {tmod.shape}, "
        f"tsdem: {tsd.shape}"
    )

    # 2) Mapear
    t1 = time.perf_counter()
    mapped = map_enif_to_mihac(tmod, tsd)
    t2 = time.perf_counter()
    print(
        f"Mapeo completo — {len(mapped):,} filas en "
        f"{t2-t1:.2f} s"
    )

    # 3) Guardar enif_mapped.csv
    out_mapped = _REPORTS_DIR / "enif_mapped.csv"
    mapped.to_csv(out_mapped, index=False, encoding="utf-8")
    print(f"  → {out_mapped} ({out_mapped.stat().st_size/1024:.1f} KB)")

    # 4) Evaluar con InferenceEngine
    t3 = time.perf_counter()
    engine = InferenceEngine()
    evaluations = _evaluate_all(mapped, engine)
    t4 = time.perf_counter()
    print(
        f"Evaluación completa — {len(evaluations):,} filas "
        f"en {t4-t3:.2f} s ({(t4-t3)/len(evaluations)*1000:.2f} ms/fila)"
    )

    # 5) Guardar enif_evaluations.csv
    out_eval = _REPORTS_DIR / "enif_evaluations.csv"
    evaluations.to_csv(out_eval, index=False, encoding="utf-8")
    print(f"  → {out_eval} ({out_eval.stat().st_size/1024:.1f} KB)")

    # 6) Reporte Markdown
    elapsed = time.perf_counter() - t0
    md = _build_stats_md(mapped, evaluations, elapsed)
    out_md = _REPORTS_DIR / "mapping_stats.md"
    out_md.write_text(md, encoding="utf-8")
    print(f"  → {out_md} ({out_md.stat().st_size/1024:.1f} KB)")

    # 7) Resumen en consola
    print("\n" + "─" * 70)
    print("RESUMEN")
    print("─" * 70)
    dist = evaluations["dictamen"].value_counts().to_dict()
    n = len(evaluations)
    for d in ("APROBADO", "REVISION_MANUAL", "RECHAZADO", "ERROR"):
        c = dist.get(d, 0)
        if c:
            print(f"  {d:18s} {c:>6,}  ({c/n*100:5.2f}%)")
    print(
        f"\n  Tiempo total: {elapsed:.2f} s  "
        f"(carga + mapeo + evaluación + persistencia)"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()
