# ============================================================
# MIHAC v2.0 — Backtesting con dataset ENIF 2024 (México)
# validation/backtesting_mx.py
# ============================================================
# Espejo del Backtester del German Credit pero corriendo sobre
# las 5,248 personas observables de ENIF (con al menos un
# crédito vigente y, por tanto, con outcome de pago observable).
#
# DERIVACIÓN DEL TARGET y_real:
#   y_real = 1  si tiene ≥1 crédito en p6_2_x  AND  ningún
#               p6_3_x == 1 (sin atrasos autodeclarados)
#   y_real = 0  si tiene ≥1 crédito  AND  algún p6_3_x == 1
#   y_real = NA si no tiene crédito vigente (no observable)
#   → Solo el subconjunto con y_real ∈ {0,1} entra al backtest.
#
# CONVENCIÓN (idéntica al backtester German):
#   y_real = 1 → buen pagador
#   y_real = 0 → mal pagador
#   y_pred = 1 → APROBADO por MIHAC
#   y_pred = 0 → RECHAZADO o REVISION_MANUAL
#   scores = score_final (0–100), normalizado a 0–1 dentro de
#            MIHACMetrics.calculate_all() para AUC-ROC.
#
# DATA LEAKAGE (caveat metodológico):
#   La variable derivada `historial_crediticio` (input de MIHAC)
#   se construye desde los mismos p6_3_x que originan y_real.
#   Esto introduce dependencia entre features y target. Los
#   resultados deben leerse como "qué tan consistente es MIHAC
#   con la mora autodeclarada", no como "qué tan bien predice
#   default futuro". El German Credit Dataset tiene el mismo
#   acoplamiento (A1, A3 vs clase). Documentado en el reporte.
# ============================================================

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_VAL_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _VAL_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from data.mapper_enif import load_enif_tables  # noqa: E402
from validation.metrics import MIHACMetrics, MIHACPlots  # noqa: E402

logger = logging.getLogger(__name__)

_REPORTS_DIR = _PROJECT_ROOT / "reports"
_OUT_DIR = _REPORTS_DIR / "backtesting_mx"

_COLS_TENENCIA = [f"p6_2_{i}" for i in range(1, 10)]
_COLS_ATRASO = [f"p6_3_{i}" for i in range(1, 10)]


# ── Construcción del target ──────────────────────────────────

def build_target(tmodulo: pd.DataFrame) -> pd.DataFrame:
    """Construye y_real a partir de p6_2_x (tenencia) y p6_3_x (atraso).

    Args:
        tmodulo: Tabla del módulo financiero ENIF 2024.

    Returns:
        DataFrame con columnas:
            llavemod, tiene_credito, algun_atraso, y_real
        donde y_real ∈ {0, 1, pd.NA}.
    """
    tiene = (tmodulo[_COLS_TENENCIA] == 1).any(axis=1)
    atraso = (tmodulo[_COLS_ATRASO] == 1).any(axis=1)

    y_real = pd.Series(
        pd.NA, index=tmodulo.index, dtype="Int64"
    )
    y_real[tiene & atraso] = 0   # mal pagador
    y_real[tiene & ~atraso] = 1  # buen pagador

    return pd.DataFrame(
        {
            "llavemod": tmodulo["llavemod"].values,
            "tiene_credito": tiene.values,
            "algun_atraso": atraso.values,
            "y_real": y_real.values,
        }
    )


# ── Análisis de errores (FP / FN) ────────────────────────────

def analyze_errors(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Separa Falsos Positivos y Falsos Negativos con perfil promedio.

    Args:
        df: DataFrame con y_real, y_pred, score_final, dti_ratio,
            edad, ingreso_mensual, proposito_credito, dictamen.

    Returns:
        (fp_df, fn_df, perfil_dict)
    """
    fp = df[(df["y_pred"] == 1) & (df["y_real"] == 0)].copy()
    fn = df[(df["y_pred"] == 0) & (df["y_real"] == 1)].copy()

    perfil: dict[str, Any] = {}
    if len(fp):
        perfil["fp"] = {
            "n": len(fp),
            "edad_prom": float(fp["edad"].mean()),
            "ingreso_prom": float(fp["ingreso_mensual"].mean()),
            "dti_prom": float(fp["dti_ratio"].mean()),
            "score_prom": float(fp["score_final"].mean()),
            "proposito_top": (
                fp["proposito_credito"].value_counts().idxmax()
            ),
        }
    if len(fn):
        perfil["fn"] = {
            "n": len(fn),
            "edad_prom": float(fn["edad"].mean()),
            "ingreso_prom": float(fn["ingreso_mensual"].mean()),
            "dti_prom": float(fn["dti_ratio"].mean()),
            "score_prom": float(fn["score_final"].mean()),
            "rechazados": int((fn["dictamen"] == "RECHAZADO").sum()),
            "revision": int(
                (fn["dictamen"] == "REVISION_MANUAL").sum()
            ),
        }
    return fp, fn, perfil


# ── Lectura del baseline German (para comparativa) ───────────

def parse_german_summary(path: Path) -> dict[str, float]:
    """Extrae métricas del report_summary.txt del backtest German."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    out: dict[str, float] = {}
    for key in (
        "accuracy",
        "precision",
        "recall",
        "f1_score",
        "specificity",
        "auc_roc",
        "costo_asimetrico",
    ):
        for line in text.splitlines():
            line = line.strip()
            if line.startswith(f"{key}:"):
                try:
                    out[key] = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
                break
    # Distribución de dictámenes
    for line in text.splitlines():
        line = line.strip()
        for d in ("APROBADO", "RECHAZADO", "REVISION_MANUAL"):
            if line.startswith(f"{d}:"):
                try:
                    n = int(line.split(":", 1)[1].split("(")[0].strip())
                    out[f"n_{d.lower()}"] = n
                except ValueError:
                    pass
    return out


# ── Reporte Markdown (comparativo + 2 párrafos académicos) ───

def build_markdown_report(
    metricas: dict[str, Any],
    perfil: dict[str, Any],
    n_total: int,
    n_observables: int,
    elapsed: float,
    german: dict[str, float],
) -> str:
    """Construye reports/backtesting_mx.md con tabla comparativa."""
    cm = metricas["matriz"]
    L: list[str] = []

    L.append("# Backtesting MIHAC v1.0 con ENIF 2024 (México) — Reporte\n")
    L.append(
        "**Generado:** "
        f"{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}  \n"
    )
    L.append(f"**Universo ENIF:** {n_total:,} personas seleccionadas  \n")
    L.append(
        f"**Población observable** (con ≥1 crédito vigente): "
        f"{n_observables:,} ({n_observables/n_total*100:.2f}%)  \n"
    )
    L.append(f"**Tiempo de ejecución:** {elapsed:.2f} s  \n\n")

    L.append("## 1. Construcción del target\n\n")
    L.append(
        "El target binario se construye desde la mora "
        "autodeclarada en ENIF (p6_3_x):\n\n"
        "- `y_real = 1` (buen pagador): tiene ≥1 crédito en "
        "p6_2_x y ningún p6_3_x == 1.\n"
        "- `y_real = 0` (mal pagador): tiene ≥1 crédito y "
        "al menos un p6_3_x == 1.\n"
        "- Personas sin crédito vigente quedan fuera del "
        "backtest (no hay outcome observable).\n\n"
    )

    pos = (cm["VP"] + cm["FN"])
    neg = (cm["FP"] + cm["VN"])
    L.append(
        f"**Distribución del target** (n={n_observables:,}):\n\n"
        f"- Buenos pagadores (y=1): {pos:,} "
        f"({pos/n_observables*100:.1f}%)\n"
        f"- Malos pagadores  (y=0): {neg:,} "
        f"({neg/n_observables*100:.1f}%)\n\n"
        f"Tasa de mora autodeclarada: "
        f"{neg/n_observables*100:.2f}% — comparar con IMOR "
        f"CNBV (microcréditos) = 3.5%. La diferencia se debe a "
        f"que ENIF capta mora autodeclarada amplia, mientras "
        f"que IMOR mide cartera vencida ≥90 días en banca "
        f"formal.\n\n"
    )

    L.append("## 2. Métricas de desempeño del motor\n\n")
    L.append("| Métrica | Valor |\n|---|---:|\n")
    L.append(f"| Accuracy | {metricas['accuracy']:.4f} |\n")
    L.append(f"| Precision | {metricas['precision']:.4f} |\n")
    L.append(f"| Recall (Sensibilidad) | {metricas['recall']:.4f} |\n")
    L.append(f"| Specificity | {metricas['specificity']:.4f} |\n")
    L.append(f"| F1-Score | {metricas['f1_score']:.4f} |\n")
    L.append(f"| AUC-ROC | {metricas['auc_roc']:.4f} |\n")
    L.append(
        f"| Costo asimétrico (4:1) | "
        f"{metricas['costo_asimetrico']:.4f} |\n\n"
    )

    L.append("### Matriz de confusión\n\n")
    L.append(
        "|  | Predicho APROBAR | Predicho RECHAZAR |\n"
        "|---|---:|---:|\n"
        f"| **Real bueno (y=1)** | VP = {cm['VP']:,} | "
        f"FN = {cm['FN']:,} |\n"
        f"| **Real malo (y=0)**  | FP = {cm['FP']:,} | "
        f"VN = {cm['VN']:,} |\n\n"
    )

    L.append("## 3. Comparativa contra German Credit Dataset\n\n")
    L.append(
        "| Métrica | MIHAC sobre German (1994, alemán) | "
        "MIHAC sobre ENIF (2024, mexicano) | Δ |\n"
        "|---|---:|---:|---:|\n"
    )
    for k, label in [
        ("accuracy", "Accuracy"),
        ("precision", "Precision"),
        ("recall", "Recall"),
        ("f1_score", "F1-Score"),
        ("specificity", "Specificity"),
        ("auc_roc", "AUC-ROC"),
        ("costo_asimetrico", "Costo asim."),
    ]:
        g = german.get(k, np.nan)
        m = metricas[k]
        delta = m - g if not np.isnan(g) else np.nan
        delta_str = f"{delta:+.4f}" if not np.isnan(delta) else "—"
        g_str = f"{g:.4f}" if not np.isnan(g) else "—"
        L.append(f"| {label} | {g_str} | {m:.4f} | {delta_str} |\n")
    L.append("\n")

    L.append("## 4. Análisis de errores\n\n")
    if "fp" in perfil:
        fp = perfil["fp"]
        L.append(
            f"**Falsos Positivos (n={fp['n']:,})** — el motor "
            "aprobó a un mal pagador (riesgo de pérdida directa):\n\n"
            f"- Edad promedio:    {fp['edad_prom']:.1f} años\n"
            f"- Ingreso promedio: ${fp['ingreso_prom']:,.0f}\n"
            f"- DTI promedio:     {fp['dti_prom']:.2f}\n"
            f"- Score promedio:   {fp['score_prom']:.1f}\n"
            f"- Propósito top:    {fp['proposito_top']}\n\n"
        )
    else:
        L.append(
            "**Falsos Positivos: 0** — el motor no aprobó "
            "a ningún mal pagador en el subconjunto observable. "
            "Precision = 1.000 (perfecta).\n\n"
        )
    if "fn" in perfil:
        fn = perfil["fn"]
        L.append(
            f"**Falsos Negativos (n={fn['n']:,})** — el motor "
            "rechazó a un buen pagador (oportunidad perdida):\n\n"
            f"- Edad promedio:    {fn['edad_prom']:.1f} años\n"
            f"- Ingreso promedio: ${fn['ingreso_prom']:,.0f}\n"
            f"- DTI promedio:     {fn['dti_prom']:.2f}\n"
            f"- Score promedio:   {fn['score_prom']:.1f}\n"
            f"- Rechazados directos: {fn['rechazados']:,}\n"
            f"- Revisión manual:    {fn['revision']:,}\n\n"
        )

    L.append("## 5. Caveats metodológicos\n\n")
    L.append(
        "1. **Acoplamiento feature-target.** La variable de "
        "entrada `historial_crediticio` se deriva desde los "
        "mismos `p6_3_x` que generan `y_real`. Las reglas R001 "
        "(historial Bueno → +20) y R002 (historial Malo → −25) "
        "introducen dependencia mecánica con el target. El "
        "German Credit Dataset tiene un acoplamiento análogo "
        "(A1, A3 son tanto entradas como originadores de la "
        "etiqueta). Las métricas reflejan **consistencia con "
        "la mora autodeclarada**, no capacidad predictiva pura.\n\n"
        "2. **Sesgo de selección.** ENIF observa solo a personas "
        "con crédito ya colocado, que han pasado filtros de "
        "los originadores. El backtest no contempla a "
        "solicitantes rechazados antes del crédito.\n\n"
        "3. **Variables imputadas.** `total_deuda_actual` y "
        "`monto_credito` son sintéticos (DTI=0.30 y medianas "
        "CNBV por propósito). `antiguedad_laboral` se deriva "
        "de p3_10 × p3_13. Estas imputaciones suprimen R011, "
        "R013, R014 y el veto DTI por diseño.\n\n"
        "4. **Granularidad reducida.** `tipo_vivienda` colapsa "
        "Rentada/Prestada en 'Familiar'. `proposito_credito` "
        "se infiere del tipo de crédito tenido — 97.7% queda "
        "como 'Consumo' por el dominio del crédito de tienda/"
        "tarjeta en la población ENIF.\n\n"
    )

    L.append("## 6. Texto para artículo académico (2 párrafos)\n\n")
    L.append(
        "> **Aplicación de MIHAC sobre datos mexicanos.** Para "
        "evaluar la transferibilidad del motor heurístico, se "
        f"corrió MIHAC v1.0 sobre {n_observables:,} personas "
        "de la Encuesta Nacional de Inclusión Financiera 2024 "
        "(INEGI) con outcome de pago observable. La derivación "
        "del target se construyó a partir de la mora "
        "autodeclarada en los nueve indicadores p6_3_x del "
        f"módulo de crédito; resultando en {pos:,} buenos "
        f"pagadores y {neg:,} casos con atraso "
        f"({neg/n_observables*100:.1f}%). El motor alcanzó "
        f"Accuracy={metricas['accuracy']:.3f}, "
        f"Precision={metricas['precision']:.3f}, "
        f"Recall={metricas['recall']:.3f}, "
        f"F1={metricas['f1_score']:.3f} y "
        f"AUC-ROC={metricas['auc_roc']:.3f} bajo la convención "
        "habitual (REVISIÓN_MANUAL contado como rechazo). La "
        "comparación contra el backtest sobre German Credit "
        f"(Accuracy={german.get('accuracy', float('nan')):.3f}, "
        f"AUC={german.get('auc_roc', float('nan')):.3f}) muestra "
        "que las reglas heurísticas calibradas para banca "
        "alemana 1994 conservan capacidad discriminatoria "
        "moderada en el contexto mexicano contemporáneo.\n\n"
    )
    L.append(
        "> **Limitaciones y trabajo futuro.** Tres factores "
        "moderan estas conclusiones. Primero, el target y la "
        "variable `historial_crediticio` comparten origen en "
        "p6_3_x, lo que introduce un acoplamiento mecánico "
        "vía las reglas R001 y R002 — las métricas miden "
        "consistencia interna más que poder predictivo "
        "verdadero. Segundo, el monto absoluto de deuda no se "
        "captura en ENIF; la imputación con DTI=0.30 sintético "
        "desactiva por diseño tres reglas de compensación "
        "(R011, R013, R014) y el veto DTI, lo que reduce la "
        "expresividad del motor en este dataset. Tercero, "
        "ENIF observa cartera ya colocada, con sesgo de "
        "selección hacia perfiles que pasaron filtros previos. "
        "La calibración con datos CNBV (Módulo G del plan v2) "
        "y la incorporación de un modelo ML supervisado "
        "(Módulo C) son los siguientes pasos propuestos para "
        "controlar estos sesgos y elevar la capacidad "
        "discriminatoria por encima de AUC=0.70.\n"
    )

    return "".join(L)


# ── Main ─────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-25s | %(message)s",
    )
    print("=" * 70)
    print("MIHAC v2.0 — Backtesting con ENIF 2024 (México)")
    print("=" * 70)

    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()

    # 1) Cargar artefactos del Módulo A + tmodulo crudo
    mapped = pd.read_csv(_REPORTS_DIR / "enif_mapped.csv")
    evals = pd.read_csv(_REPORTS_DIR / "enif_evaluations.csv")
    print(
        f"\nMódulo A cargado — mapped: {mapped.shape}, "
        f"evals: {evals.shape}"
    )

    tmod, _ = load_enif_tables()

    # 2) Construir target
    target = build_target(tmod)
    print(
        f"Target construido — observables: "
        f"{target['y_real'].notna().sum():,} de {len(target):,}"
    )

    # 3) Unir y filtrar a observables
    df = (
        mapped.merge(evals, on="llavemod", how="inner")
        .merge(target, on="llavemod", how="inner")
    )
    obs = df[df["y_real"].notna()].copy()
    obs["y_real"] = obs["y_real"].astype(int)
    obs["y_pred"] = (obs["dictamen"] == "APROBADO").astype(int)
    print(
        f"Backtest sobre {len(obs):,} filas "
        f"(buenos={int((obs['y_real']==1).sum()):,}, "
        f"malos={int((obs['y_real']==0).sum()):,})"
    )

    # 4) Métricas (reusa MIHACMetrics ya validada por German)
    m = MIHACMetrics()
    metricas = m.calculate_all(
        y_real=obs["y_real"].values,
        y_pred=obs["y_pred"].values,
        scores=obs["score_final"].values,
        dictamenes=obs["dictamen"].tolist(),
    )

    print(
        f"\nMétricas — Acc={metricas['accuracy']:.4f}  "
        f"P={metricas['precision']:.4f}  "
        f"R={metricas['recall']:.4f}  "
        f"F1={metricas['f1_score']:.4f}  "
        f"AUC={metricas['auc_roc']:.4f}"
    )
    cm = metricas["matriz"]
    print(
        f"Matriz: VP={cm['VP']}  FP={cm['FP']}  "
        f"VN={cm['VN']}  FN={cm['FN']}"
    )

    # 5) Análisis de errores y persistencia
    fp_df, fn_df, perfil = analyze_errors(obs)
    fp_df.to_csv(_OUT_DIR / "errores_fp.csv", index=False, encoding="utf-8")
    fn_df.to_csv(_OUT_DIR / "errores_fn.csv", index=False, encoding="utf-8")
    obs.to_csv(_OUT_DIR / "results.csv", index=False, encoding="utf-8")

    # 6) Plots (reutiliza MIHACPlots del backtester German)
    plots = MIHACPlots()
    y_r = obs["y_real"].values
    y_p = obs["y_pred"].values
    sc = obs["score_final"].values

    plots.plot_confusion_matrix(
        metricas, str(_OUT_DIR / "confusion_matrix.png")
    )
    plots.plot_roc_curve(
        y_r, sc, str(_OUT_DIR / "roc_curve.png")
    )
    plots.plot_score_distribution(
        sc, y_r, str(_OUT_DIR / "score_distribution.png")
    )
    plots.plot_precision_recall_curve(
        y_r, sc, str(_OUT_DIR / "precision_recall.png")
    )
    plots.plot_metrics_dashboard(
        metricas, y_r, sc, str(_OUT_DIR / "dashboard.png")
    )
    print(f"\n5 plots guardados en {_OUT_DIR}")

    # 7) Reporte Markdown comparativo
    german = parse_german_summary(
        _REPORTS_DIR / "backtesting" / "report_summary.txt"
    )
    print(
        f"\nBaseline German cargado: "
        f"{ {k:v for k,v in german.items() if k in ('accuracy','auc_roc','f1_score')} }"
    )

    elapsed = time.perf_counter() - t0
    md = build_markdown_report(
        metricas, perfil, len(tmod), len(obs), elapsed, german
    )
    out_md = _REPORTS_DIR / "backtesting_mx.md"
    out_md.write_text(md, encoding="utf-8")
    print(f"\nReporte Markdown → {out_md}")

    # 8) Resumen consola
    print("\n" + "─" * 70)
    print("RESUMEN")
    print("─" * 70)
    print(f"  Población observable: {len(obs):,}")
    print(
        f"  Distribución dictamen: "
        f"APROBADO={int((obs['dictamen']=='APROBADO').sum()):,}, "
        f"REVISION={int((obs['dictamen']=='REVISION_MANUAL').sum()):,}, "
        f"RECHAZADO={int((obs['dictamen']=='RECHAZADO').sum()):,}"
    )
    print(f"  Tiempo total: {elapsed:.2f} s")
    print("=" * 70)


if __name__ == "__main__":
    main()
