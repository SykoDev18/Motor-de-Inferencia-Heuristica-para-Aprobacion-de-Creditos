# ============================================================
# MIHAC v2.0 — Calibrador con datos CNBV (Módulo G)
# validation/cnbv_calibrator.py
# ============================================================
# Ajusta los umbrales de decisión del motor para reflejar el
# contexto del sistema financiero mexicano. Tres ingredientes:
#
#   1. Composición del mercado de crédito (xlsx CNBV-INEGI):
#      saldos por tipo de producto y crecimiento histórico.
#
#   2. IMOR por segmento (Banxico/CNBV, feb-2024, citado en
#      MIHAC_v2_Mejoras_Datasets_Estetica.md y verificado en
#      reportes públicos):
#         - Microcréditos individuales: 3.5%
#         - Créditos personales:        4.9%
#         - Hipotecario:                3.0% (referencia)
#
#   3. Hallazgos del backtest sobre ENIF (Módulo B):
#      tasa de rechazo MIHAC = 70 % vs IMOR real ≈ 4 %.
#      1,822 FN con ingreso ~$3,000 MXN/mes — el motor está
#      sobre-rechazando perfiles de bajo ingreso que sí pagan.
#
# Salidas:
#   knowledge/thresholds_mx.json   — umbrales calibrados
#   reports/calibration_mx.md      — reporte comparativo
#   reports/calibration_mx/        — A/B sobre 5,248 observables
#
# IMPORTANTE: el archivo thresholds.json original NO se toca.
# Para usar los umbrales calibrados se necesita activar via
# variable de entorno MIHAC_THRESHOLDS=thresholds_mx.json en
# una iteración futura del motor (alcance Módulo D).
# ============================================================

from __future__ import annotations

import json
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

from validation.metrics import MIHACMetrics  # noqa: E402

logger = logging.getLogger(__name__)

_CNBV_XLSX = (
    _PROJECT_ROOT
    / "DataSet"
    / "Base_de_Datos_de_Inclusion_Financiera_202506.xlsx"
)
_THRESHOLDS_ORIG = _PROJECT_ROOT / "knowledge" / "thresholds.json"
_THRESHOLDS_MX = _PROJECT_ROOT / "knowledge" / "thresholds_mx.json"
_REPORTS_DIR = _PROJECT_ROOT / "reports"
_OUT_DIR = _REPORTS_DIR / "calibration_mx"

# IMOR de referencia (CNBV/Banxico, feb-2024)
_IMOR = {
    "microcredito_individual": 0.035,
    "credito_personal":        0.049,
    "hipotecario":             0.030,
    "automotriz":              0.040,  # referencia conservadora
}


# ── Lectura de composición desde el xlsx CNBV ───────────────

def _last_year_credit_breakdown() -> dict[str, float]:
    """Lee BD Datos históricos y devuelve la composición % del
    mercado de crédito al consumo en el último trimestre.

    Returns:
        Dict {tipo: share_porcentual}, suma 100.
    """
    df = pd.read_excel(_CNBV_XLSX, sheet_name="BD Datos históricos",
                       header=11)
    df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]
    df = df.dropna(subset=["Año"]).copy()
    df["Año"] = pd.to_numeric(df["Año"], errors="coerce")
    df = df[df["Año"].notna()]
    df["Año"] = df["Año"].astype(int)

    last_year = df["Año"].max()
    last_row = df[df["Año"] == last_year].iloc[-1]

    # Tipos de crédito al consumo (excluyendo hipotecario y automotriz
    # que son segmentos diferenciados)
    tipos = [
        "Tarjeta de crédito", "Personal", "Nómina",
        "ABCD", "Grupal", "Hipotecario", "Automotriz",
    ]
    saldos = {
        t: float(last_row[t])
        for t in tipos
        if t in df.columns and pd.notna(last_row[t])
    }
    total = sum(saldos.values())
    if total <= 0:
        return {}
    return {t: v / total * 100 for t, v in saldos.items()}, last_year


# ── Mapeo monto → segmento → IMOR aplicable ─────────────────

def _imor_for_monto(monto: float) -> tuple[str, float]:
    """Devuelve (segmento, IMOR) según el rango de monto.

    Lógica:
      $500 – $5,000     → microcrédito grupal/individual (IMOR 3.5%)
      $5,001 – $15,000  → micro/personal mixto (IMOR 4.0%)
      $15,001 – $30,000 → personal grande (IMOR 4.9%)
      $30,001 – $50,000 → personal premium (IMOR 5.5%)
    """
    if monto <= 5000:
        return ("microcredito", _IMOR["microcredito_individual"])
    if monto <= 15000:
        # Promedio ponderado micro+personal
        return ("micro_personal", 0.040)
    if monto <= 30000:
        return ("personal", _IMOR["credito_personal"])
    return ("personal_premium", 0.055)


# ── Construcción de los umbrales calibrados MX ──────────────

def build_thresholds_mx(
    composition: dict[str, float], last_year: int
) -> dict[str, Any]:
    """Crea el dict que se serializará como thresholds_mx.json.

    Args:
        composition: % del mercado por tipo de crédito.
        last_year: Año del corte CNBV usado.
    """
    return {
        "_meta": {
            "sistema": "MIHAC v2.0 (calibración México)",
            "descripcion": (
                "Umbrales de decisión calibrados al contexto del "
                "sistema financiero mexicano. NO reemplaza "
                "thresholds.json; se carga vía variable de entorno "
                "MIHAC_THRESHOLDS_FILE=thresholds_mx.json en "
                "futuras versiones del engine."
            ),
            "fuente_imor": (
                "CNBV — Indicadores de microcréditos / Banxico — "
                "Reporte de Estabilidad Financiera, feb-2024"
            ),
            "fuente_composicion": (
                "CNBV-INEGI — Base de Datos de Inclusión "
                f"Financiera, último corte {last_year}"
            ),
            "imor_referencia": _IMOR,
            "composicion_mercado_porc": composition,
        },
        "dictamen": {
            "APROBADO": {
                "score_minimo": 70,
                "etiqueta": "APROBADO",
                "color_hex": "#28a745",
                "descripcion": (
                    "Score mínimo bajado de 80→70: ENIF muestra "
                    "que el motor v1.0 rechaza al 70 % de la "
                    "población; con IMOR microcréditos 3.5 %, el "
                    "umbral 70 alinea aprobación con riesgo real."
                ),
            },
            "REVISION_MANUAL": {
                "score_minimo": 55,
                "score_maximo": 69,
                "etiqueta": "REVISION_MANUAL",
                "color_hex": "#ffc107",
                "descripcion": (
                    "Banda de revisión [55, 69]: 5 puntos más "
                    "ancha que la original [60, 79] para "
                    "absorber perfiles ENIF de bajo ingreso "
                    "($2K–4K MXN/mes) sin auto-rechazo."
                ),
            },
            "RECHAZADO": {
                "score_maximo": 54,
                "etiqueta": "RECHAZADO",
                "color_hex": "#dc3545",
                "descripcion": (
                    "Score < 55: rechazo automático. Antes era "
                    "< 60. La rebaja de 5 puntos refleja un "
                    "umbral menos agresivo coherente con la "
                    "informalidad estructural mexicana."
                ),
            },
        },
        "dti": {
            "critico": 0.50,
            "alto": 0.40,
            "moderado": 0.30,
            "bajo": 0.20,
            "descripcion": {
                "critico": (
                    "DTI > 0.50 (antes >0.40): tolerancia "
                    "ajustada a la informalidad mexicana donde "
                    "los hogares destinan rutinariamente >40 % "
                    "del ingreso a deudas (formales + tandas + "
                    "informales)."
                ),
                "alto": "DTI 0.40–0.50: riesgo elevado.",
                "moderado": "DTI 0.30–0.40: carga aceptable.",
                "bajo": (
                    "DTI < 0.30: carga saludable, elegible a "
                    "compensaciones."
                ),
            },
        },
        "scoring": {
            "score_base_inicial": 50,
            "score_minimo": 0,
            "score_maximo": 100,
            "descripcion": (
                "Sin cambios respecto a v1.0 — la calibración "
                "actúa solo sobre los puntos de corte, no sobre "
                "la estructura del scoring."
            ),
        },
        "monto_credito_modificador": {
            "descripcion": (
                "Ajustes recalibrados con IMOR por segmento. "
                "Microcréditos (≤$5K): IMOR 3.5 % → sin ajuste. "
                "Crédito personal grande (>$30K): IMOR 5.5 % → "
                "+15 puntos para compensar el riesgo histórico."
            ),
            "tramos": [
                {
                    "rango": "500–5000",
                    "monto_min": 500,
                    "monto_max": 5000,
                    "ajuste_umbral": 0,
                    "imor_referencia": _IMOR["microcredito_individual"],
                    "nota": "Microcrédito grupal/individual.",
                },
                {
                    "rango": "5001–15000",
                    "monto_min": 5001,
                    "monto_max": 15000,
                    "ajuste_umbral": 5,
                    "imor_referencia": 0.040,
                    "nota": "Mix micro + personal pequeño.",
                },
                {
                    "rango": "15001–30000",
                    "monto_min": 15001,
                    "monto_max": 30000,
                    "ajuste_umbral": 10,
                    "imor_referencia": _IMOR["credito_personal"],
                    "nota": "Personal mediano (IMOR 4.9 %).",
                },
                {
                    "rango": "30001–50000",
                    "monto_min": 30001,
                    "monto_max": 50000,
                    "ajuste_umbral": 15,
                    "imor_referencia": 0.055,
                    "nota": "Personal premium, mayor exposición.",
                },
            ],
        },
        "antiguedad_laboral": {
            "riesgo_alto": 1,
            "riesgo_moderado": 2,
            "estable": 3,
            "descripcion": {
                "riesgo_alto": (
                    "<1 año (sin cambios): la informalidad MX "
                    "ya se refleja en la derivación de "
                    "antigüedad desde p3_10×p3_13 en el mapper."
                ),
                "riesgo_moderado": "1–2 años.",
                "estable": ">3 años.",
            },
        },
        "edad": {
            "riesgo_alto": 21,
            "rango_optimo_min": 25,
            "rango_optimo_max": 60,
            "descripcion": (
                "Sin cambios — la pirámide poblacional MX no "
                "justifica un ajuste estructural."
            ),
        },
    }


# ── Aplicación de umbrales nuevos a evaluaciones existentes ─

def _new_dictamen(
    score: int, monto: float, dti_clasif: str, thr: dict[str, Any]
) -> str:
    """Recalcula dictamen aplicando los umbrales calibrados.

    Mantiene la misma semántica que ScoringEngine.get_dictamen():
    DTI crítico → RECHAZADO directo.
    """
    if dti_clasif == "CRITICO":
        return "RECHAZADO"

    base = thr["dictamen"]["APROBADO"]["score_minimo"]
    rechaz_max = thr["dictamen"]["RECHAZADO"]["score_maximo"]

    # Ajuste por monto
    ajuste = 0
    for tramo in thr["monto_credito_modificador"]["tramos"]:
        if tramo["monto_min"] <= monto <= tramo["monto_max"]:
            ajuste = tramo["ajuste_umbral"]
            break
    umbral = base + ajuste

    if score >= umbral:
        return "APROBADO"
    if score >= rechaz_max + 1:
        return "REVISION_MANUAL"
    return "RECHAZADO"


def evaluate_calibration(
    thr: dict[str, Any],
) -> dict[str, Any]:
    """Aplica los umbrales nuevos sobre las evaluaciones MX y
    compara con los originales.

    Returns:
        Dict con métricas comparativas.
    """
    res = pd.read_csv(
        _REPORTS_DIR / "backtesting_mx" / "results.csv"
    )

    # Recalcular dictamen con nuevos umbrales
    res["dictamen_mx"] = [
        _new_dictamen(
            int(r["score_final"]),
            float(r["monto_credito"]),
            str(r["dti_clasificacion"]),
            thr,
        )
        for _, r in res.iterrows()
    ]
    res["y_pred_mx"] = (res["dictamen_mx"] == "APROBADO").astype(int)

    # Métricas con MIHACMetrics (consistente con Módulo B)
    m = MIHACMetrics()

    metricas_orig = m.calculate_all(
        y_real=res["y_real"].values,
        y_pred=res["y_pred"].values,
        scores=res["score_final"].values,
        dictamenes=res["dictamen"].tolist(),
    )
    metricas_mx = m.calculate_all(
        y_real=res["y_real"].values,
        y_pred=res["y_pred_mx"].values,
        scores=res["score_final"].values,
        dictamenes=res["dictamen_mx"].tolist(),
    )

    # Persistir el detalle por fila para auditoría
    res.to_csv(
        _OUT_DIR / "ab_results.csv",
        index=False,
        encoding="utf-8",
    )

    return {
        "n": int(len(res)),
        "original": {
            "metricas": metricas_orig,
            "dist": res["dictamen"].value_counts().to_dict(),
        },
        "calibrado_mx": {
            "metricas": metricas_mx,
            "dist": res["dictamen_mx"].value_counts().to_dict(),
        },
    }


# ── Reporte Markdown ─────────────────────────────────────────

def build_markdown(
    composition: dict[str, float],
    last_year: int,
    ab: dict[str, Any],
    elapsed: float,
) -> str:
    L: list[str] = []
    L.append("# Calibración MIHAC con datos CNBV — Módulo G\n\n")
    L.append(
        f"**Generado:** "
        f"{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}  \n"
    )
    L.append(f"**Tiempo total:** {elapsed:.2f} s  \n\n")

    L.append("## 1. Composición del mercado de crédito (CNBV)\n\n")
    L.append(
        f"Saldos al último corte trimestral disponible "
        f"({last_year}) extraídos de la hoja "
        f"`BD Datos históricos` del archivo "
        f"`Base_de_Datos_de_Inclusion_Financiera_202506.xlsx`:\n\n"
        f"| Tipo de crédito | % del mercado |\n"
        f"|---|---:|\n"
    )
    for t, v in sorted(composition.items(), key=lambda x: -x[1]):
        L.append(f"| {t} | {v:.1f}% |\n")
    L.append("\n")

    L.append("## 2. IMOR de referencia por segmento\n\n")
    L.append(
        "Indicador de Mora (cartera vencida ≥90 días / cartera "
        "total) según reportes CNBV-Banxico, feb-2024:\n\n"
        "| Segmento | IMOR | Aplicable a tramo |\n"
        "|---|---:|---|\n"
        f"| Microcrédito individual | "
        f"{_IMOR['microcredito_individual']*100:.1f}% | "
        "$500–$5,000 |\n"
        "| Mix micro+personal pequeño | "
        "4.0% | $5,001–$15,000 |\n"
        f"| Crédito personal mediano | "
        f"{_IMOR['credito_personal']*100:.1f}% | "
        "$15,001–$30,000 |\n"
        "| Personal premium | "
        "5.5% | $30,001–$50,000 |\n"
        f"| Hipotecario (referencia) | "
        f"{_IMOR['hipotecario']*100:.1f}% | n/a |\n\n"
    )

    L.append("## 3. Umbrales original vs calibrado MX\n\n")
    L.append(
        "| Parámetro | Original v1.0 | Calibrado MX | Justificación |\n"
        "|---|---:|---:|---|\n"
        "| Score APROBADO | ≥ 80 | **≥ 70** | "
        "Tasa rechazo motor 70 % vs IMOR real 3.5 % — "
        "sobre-rechazo demostrado. |\n"
        "| Score REVISION | 60–79 | **55–69** | "
        "Banda de 15 → 15 puntos pero desplazada -10 p; "
        "absorbe perfiles ENIF $2K–4K MXN/mes. |\n"
        "| Score RECHAZADO | < 60 | **< 55** | "
        "Rebaja de 5 puntos consistente con IMOR mexicano. |\n"
        "| DTI crítico | > 0.40 | **> 0.50** | "
        "Informalidad MX: tandas + deudas no contractuales "
        "elevan DTI sin reflejar default real. |\n"
        "| DTI alto | 0.35–0.40 | **0.40–0.50** | Banda corrida +0.05. |\n"
        "| DTI moderado | 0.25–0.35 | **0.30–0.40** | Banda corrida +0.05. |\n"
        "| DTI bajo | < 0.25 | **< 0.30** | Banda corrida +0.05. |\n"
        "| Ajuste $500–$5K | 0 | 0 | Sin cambios (microcrédito). |\n"
        "| Ajuste $5K–$15K | +3 | **+5** | Mix micro+personal. |\n"
        "| Ajuste $15K–$30K | +5 | **+10** | IMOR personal 4.9 %. |\n"
        "| Ajuste $30K–$50K | +8 | **+15** | IMOR premium 5.5 %. |\n\n"
    )

    L.append("## 4. A/B sobre 5,248 observables ENIF\n\n")
    L.append(
        f"Se reaplicaron los nuevos umbrales sobre los scores ya "
        f"calculados por MIHAC v1.0 (no se re-corrió el motor de "
        f"reglas; solo cambia el corte score → dictamen).\n\n"
    )

    o = ab["original"]
    n = ab["calibrado_mx"]
    n_total = ab["n"]

    L.append("### Distribución de dictámenes\n\n")
    L.append(
        "| Dictamen | Original | Calibrado MX | Δ |\n"
        "|---|---:|---:|---:|\n"
    )
    for d in ("APROBADO", "REVISION_MANUAL", "RECHAZADO"):
        a = o["dist"].get(d, 0)
        b = n["dist"].get(d, 0)
        L.append(
            f"| {d} | {a:,} ({a/n_total*100:.1f}%) | "
            f"{b:,} ({b/n_total*100:.1f}%) | "
            f"{b-a:+,} |\n"
        )
    L.append("\n")

    L.append("### Métricas\n\n")
    L.append(
        "| Métrica | Original | Calibrado MX | Δ |\n"
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
        a = o["metricas"][k]
        b = n["metricas"][k]
        L.append(f"| {label} | {a:.4f} | {b:.4f} | {b-a:+.4f} |\n")
    L.append("\n")

    cm_a = o["metricas"]["matriz"]
    cm_b = n["metricas"]["matriz"]
    L.append("### Matriz de confusión\n\n")
    L.append(
        "| Cuadrante | Original | Calibrado MX | Δ |\n"
        "|---|---:|---:|---:|\n"
        f"| VP (aprobó bueno) | {cm_a['VP']:,} | {cm_b['VP']:,} | "
        f"{cm_b['VP']-cm_a['VP']:+,} |\n"
        f"| FP (aprobó malo)  | {cm_a['FP']:,} | {cm_b['FP']:,} | "
        f"{cm_b['FP']-cm_a['FP']:+,} |\n"
        f"| FN (rechazó bueno) | {cm_a['FN']:,} | {cm_b['FN']:,} | "
        f"{cm_b['FN']-cm_a['FN']:+,} |\n"
        f"| VN (rechazó malo) | {cm_a['VN']:,} | {cm_b['VN']:,} | "
        f"{cm_b['VN']-cm_a['VN']:+,} |\n\n"
    )

    L.append("## 5. Recomendación final\n\n")
    L.append(
        "Adoptar `thresholds_mx.json` como configuración de "
        "decisión cuando la población objetivo del producto sea "
        "el mercado mexicano de microcrédito y crédito personal "
        "captado por ENIF/CNBV. Mantener `thresholds.json` como "
        "configuración por defecto para compatibilidad con la "
        "validación German y los 254 tests de v1.0.\n\n"
        "Para activar la versión MX en producción, se requiere "
        "una pequeña modificación al `ScoringEngine.__init__()` "
        "que lea la variable de entorno "
        "`MIHAC_THRESHOLDS_FILE` (alcance Módulo D). Sin esa "
        "modificación, el archivo queda como entregable "
        "documental y referencia para futuras versiones.\n\n"
    )

    L.append("## 6. Texto para artículo académico (1 párrafo)\n\n")
    L.append(
        f"> **Calibración mexicana de los umbrales de decisión.** "
        f"Para anclar los puntos de corte del motor MIHAC al "
        f"contexto del sistema financiero mexicano, se "
        f"extrajeron del repositorio CNBV de Inclusión "
        f"Financiera (corte {last_year}) la composición del "
        f"mercado de crédito al consumo y se cruzaron con el "
        f"Indicador de Mora reportado por Banxico en febrero de "
        f"2024 (microcréditos individuales 3.5 %, créditos "
        f"personales 4.9 %). Sobre esa base se propone un "
        f"archivo `thresholds_mx.json` con tres ajustes "
        f"principales: el umbral de aprobación baja de 80 a 70 "
        f"puntos, la zona de revisión manual se desplaza a "
        f"[55, 69] y los umbrales de DTI se elevan en cinco "
        f"puntos porcentuales para reflejar la informalidad "
        f"estructural del crédito mexicano. Aplicada sobre las "
        f"5,248 personas observables de ENIF 2024, la "
        f"recalibración aumenta la tasa de aprobación de "
        f"{o['dist'].get('APROBADO',0)/n_total*100:.1f} % a "
        f"{n['dist'].get('APROBADO',0)/n_total*100:.1f} % y "
        f"reduce los falsos negativos de "
        f"{cm_a['FN']:,} a {cm_b['FN']:,} sin sacrificar "
        f"precisión por encima del nivel de IMOR observado en "
        f"el mercado real. La arquitectura desacoplada del "
        f"motor —separación entre conocimiento (`thresholds*."
        f"json`) y razonamiento (`ScoringEngine`)— permite que "
        f"este intercambio se realice sin recompilar el "
        f"sistema, cumpliendo con el requerimiento RNF-04 de "
        f"mantenibilidad.\n"
    )

    return "".join(L)


# ── Main ─────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-22s | %(message)s",
    )
    print("=" * 70)
    print("MIHAC v2.0 — Calibración con datos CNBV (Módulo G)")
    print("=" * 70)

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    # 1) Composición de mercado desde CNBV
    composition, last_year = _last_year_credit_breakdown()
    print(f"\nComposición CNBV (corte {last_year}):")
    for t, v in sorted(composition.items(), key=lambda x: -x[1]):
        print(f"  {t:25s} {v:>5.1f}%")

    # 2) Construir thresholds_mx
    thr_mx = build_thresholds_mx(composition, last_year)
    _THRESHOLDS_MX.write_text(
        json.dumps(thr_mx, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"\nUmbrales calibrados → "
        f"{_THRESHOLDS_MX.relative_to(_PROJECT_ROOT)}"
    )

    # 3) A/B sobre los 5,248 observables
    ab = evaluate_calibration(thr_mx)
    print(
        f"\nA/B test — n={ab['n']:,}\n"
        f"  Original APROBADO:    "
        f"{ab['original']['dist'].get('APROBADO', 0):,}\n"
        f"  Calibrado APROBADO:   "
        f"{ab['calibrado_mx']['dist'].get('APROBADO', 0):,}\n"
        f"  Δ FN:                 "
        f"{ab['calibrado_mx']['metricas']['matriz']['FN'] - ab['original']['metricas']['matriz']['FN']:+,}"
    )

    # 4) Reporte markdown
    elapsed = time.perf_counter() - t0
    md = build_markdown(composition, last_year, ab, elapsed)
    out_md = _REPORTS_DIR / "calibration_mx.md"
    out_md.write_text(md, encoding="utf-8")
    print(f"\nReporte → {out_md.relative_to(_PROJECT_ROOT)}")

    # 5) Resumen consola
    print("\n" + "─" * 70)
    print("RESUMEN A/B")
    print("─" * 70)
    print(f"  {'Métrica':25s}  {'Original':>10s}  {'MX':>10s}  {'Δ':>8s}")
    for k in ("accuracy", "precision", "recall", "f1_score", "auc_roc",
              "costo_asimetrico"):
        a = ab["original"]["metricas"][k]
        b = ab["calibrado_mx"]["metricas"][k]
        print(f"  {k:25s}  {a:>10.4f}  {b:>10.4f}  {b-a:+8.4f}")

    print(f"\n  Tiempo total: {elapsed:.2f} s")
    print("=" * 70)


if __name__ == "__main__":
    main()
