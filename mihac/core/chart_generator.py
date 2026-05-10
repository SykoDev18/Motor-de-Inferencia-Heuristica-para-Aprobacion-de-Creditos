# ============================================================
# MIHAC v2.0 — Generador de specs Plotly para la UI v2
# core/chart_generator.py
# ============================================================
# Construye los `data` y `layout` de los gráficos Plotly como
# diccionarios Python que se serializan a JSON e incrustan en
# las plantillas HTML. Plotly.js (CDN) los renderiza en el
# navegador.
#
# Dos gráficos:
#   1. Waterfall — construcción del score paso a paso
#      (sub-scores acumulan desde 0; reglas activadas suman/
#      restan; total final = score_final).
#   2. Radar — perfil del solicitante en 4 dimensiones
#      (Solvencia/40, Estabilidad/30, Historial/20, Perfil/10)
#      escalado a 0-100 vs un perfil promedio de aprobado.
# ============================================================

from __future__ import annotations

from typing import Any

# Paleta consistente con el rediseño v2
_GREEN = "#10B981"
_RED = "#EF4444"
_AMBER = "#F59E0B"
_BLUE = "#1B4F8A"
_TEAL = "#0E7C7B"
_NAVY = "#0D1B2A"
_GRAY = "#94A3B8"

# Sub-score → puntaje máximo (definido en core/scorer.py)
_SUB_SCORE_MAX = {
    "solvencia": 40,
    "estabilidad": 30,
    "historial_score": 20,
    "perfil": 10,
}

_SUB_SCORE_LABELS = {
    "solvencia": "Solvencia",
    "estabilidad": "Estabilidad",
    "historial_score": "Historial",
    "perfil": "Perfil",
}

# Perfil promedio aprobado — derivado del backtest German histórico
_BENCHMARK_APROBADOS = {
    "solvencia": 75,        # 30/40 del max
    "estabilidad": 80,      # 24/30
    "historial_score": 85,  # 17/20
    "perfil": 75,           # 7.5/10
}


def build_waterfall_spec(resultado: dict) -> dict:
    """Construye spec Plotly para el gráfico waterfall.

    El waterfall acumula:
      - 4 barras de sub-scores partiendo de 0
      - 1 barra por cada regla activada (+ o − impacto)
      - total final = score_final

    Args:
        resultado: dict retornado por InferenceEngine.evaluate().

    Returns:
        Dict con `data` y `layout` listos para Plotly.newPlot().
    """
    sub_scores = resultado.get("sub_scores", {})
    reglas = resultado.get("reglas_activadas", [])
    score_final = int(resultado.get("score_final", 0))

    # Etiquetas y valores
    x_labels: list[str] = []
    y_values: list[float] = []
    measures: list[str] = []  # "absolute" | "relative" | "total"
    text_labels: list[str] = []

    for key in ("solvencia", "estabilidad", "historial_score", "perfil"):
        v = int(sub_scores.get(key, 0))
        x_labels.append(_SUB_SCORE_LABELS[key])
        y_values.append(v)
        measures.append("relative")
        text_labels.append(f"+{v}")

    # Reglas activadas (incluye compensaciones; el motor las separa
    # pero todas tienen impacto en el score)
    for r in reglas:
        impacto = int(r.get("impacto", 0))
        rid = r.get("id", "?")
        x_labels.append(rid)
        y_values.append(impacto)
        measures.append("relative")
        text_labels.append(f"{impacto:+d}")

    # Total final
    x_labels.append("Score final")
    y_values.append(score_final)
    measures.append("total")
    text_labels.append(str(score_final))

    return {
        "data": [{
            "type": "waterfall",
            "orientation": "v",
            "x": x_labels,
            "y": y_values,
            "measure": measures,
            "text": text_labels,
            "textposition": "outside",
            "increasing": {"marker": {"color": _GREEN}},
            "decreasing": {"marker": {"color": _RED}},
            "totals":     {"marker": {"color": _BLUE}},
            "connector": {
                "line": {
                    "color": _GRAY,
                    "width": 1,
                    "dash": "dot",
                },
            },
            "hovertemplate": (
                "<b>%{x}</b><br>Impacto: %{y:+d}<extra></extra>"
            ),
        }],
        "layout": {
            "title": {
                "text": "Construcción del score",
                "font": {"family": "Lexend, sans-serif", "size": 18},
            },
            "yaxis": {
                "title": "Puntos",
                "range": [0, 110],
                "gridcolor": "#E5E7EB",
            },
            "xaxis": {"tickangle": -25},
            "showlegend": False,
            "margin": {"l": 50, "r": 20, "t": 50, "b": 80},
            "plot_bgcolor": "#FFFFFF",
            "paper_bgcolor": "#FFFFFF",
            "font": {"family": "Inter, sans-serif", "size": 12},
        },
    }


def build_radar_spec(resultado: dict) -> dict:
    """Construye spec Plotly para el radar de 4 dimensiones.

    Compara el perfil del solicitante (sub-scores escalados a
    0-100) contra el promedio de aprobados (benchmark).

    Args:
        resultado: dict retornado por InferenceEngine.evaluate().

    Returns:
        Dict con `data` y `layout`.
    """
    sub_scores = resultado.get("sub_scores", {})

    categories = [_SUB_SCORE_LABELS[k] for k in (
        "solvencia", "estabilidad", "historial_score", "perfil",
    )]
    # Cerrar el polígono repitiendo el primer valor al final
    categories_closed = categories + [categories[0]]

    solicitante = []
    for k in ("solvencia", "estabilidad", "historial_score", "perfil"):
        v = int(sub_scores.get(k, 0))
        max_v = _SUB_SCORE_MAX[k]
        solicitante.append(round(v / max_v * 100, 1))
    solicitante_closed = solicitante + [solicitante[0]]

    benchmark = [
        _BENCHMARK_APROBADOS[k]
        for k in ("solvencia", "estabilidad", "historial_score", "perfil")
    ]
    benchmark_closed = benchmark + [benchmark[0]]

    return {
        "data": [
            {
                "type": "scatterpolar",
                "r": benchmark_closed,
                "theta": categories_closed,
                "fill": "toself",
                "name": "Aprobados promedio",
                "line": {"color": _GRAY},
                "fillcolor": "rgba(148, 163, 184, 0.20)",
            },
            {
                "type": "scatterpolar",
                "r": solicitante_closed,
                "theta": categories_closed,
                "fill": "toself",
                "name": "Este solicitante",
                "line": {"color": _BLUE, "width": 3},
                "fillcolor": "rgba(27, 79, 138, 0.35)",
            },
        ],
        "layout": {
            "title": {
                "text": "Perfil en 4 dimensiones",
                "font": {"family": "Lexend, sans-serif", "size": 18},
            },
            "polar": {
                "radialaxis": {
                    "visible": True,
                    "range": [0, 100],
                    "tickfont": {"size": 10},
                },
                "angularaxis": {
                    "tickfont": {"family": "Inter, sans-serif",
                                 "size": 12},
                },
            },
            "showlegend": True,
            "legend": {
                "orientation": "h",
                "yanchor": "bottom",
                "y": -0.15,
                "xanchor": "center",
                "x": 0.5,
            },
            "margin": {"l": 60, "r": 60, "t": 60, "b": 60},
            "paper_bgcolor": "#FFFFFF",
            "font": {"family": "Inter, sans-serif", "size": 12},
        },
    }


def build_charts_for_template(resultado: dict) -> dict[str, Any]:
    """Helper de conveniencia: devuelve ambos specs para Jinja2.

    Uso en template::

        {{ charts.waterfall|tojson }}
        {{ charts.radar|tojson }}
    """
    return {
        "waterfall": build_waterfall_spec(resultado),
        "radar": build_radar_spec(resultado),
    }
