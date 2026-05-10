# ============================================================
# MIHAC v1.0 — Rutas de la Aplicación Web
# app/routes.py
# ============================================================
# Blueprint principal con las rutas de la interfaz.
# ============================================================

import logging

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    send_file,
)

import os
from datetime import datetime, timedelta

from app import db
from app.forms import EvaluacionForm
from app.models import Evaluacion
from core.calibrated_engine import CalibratedEngine
from core.chart_generator import build_charts_for_template
from core.engine import InferenceEngine
from reports.pdf_report import PDFReportGenerator

logger = logging.getLogger(__name__)

main = Blueprint("main", __name__)

# Motor de inferencia (instancia única por proceso)
_engine = InferenceEngine()

# Generador de PDFs (instancia única)
_pdf_gen = PDFReportGenerator()


# ════════════════════════════════════════════════════════════
# RUTA: PÁGINA PRINCIPAL — FORMULARIO DE EVALUACIÓN
# ════════════════════════════════════════════════════════════

@main.route("/", methods=["GET", "POST"])
def index():
    """Formulario de nueva evaluación crediticia.

    GET:  Renderiza el formulario vacío.
    POST: Valida datos → ejecuta motor → guarda en BD →
          redirige a resultado.
    """
    form = EvaluacionForm()

    if form.validate_on_submit():
        # Construir dict de entrada para el motor
        datos_entrada = {
            "edad": form.edad.data,
            "ingreso_mensual": form.ingreso_mensual.data,
            "total_deuda_actual": form.total_deuda_actual.data,
            "historial_crediticio": int(
                form.historial_crediticio.data
            ),
            "antiguedad_laboral": form.antiguedad_laboral.data,
            "numero_dependientes": form.numero_dependientes.data,
            "tipo_vivienda": form.tipo_vivienda.data,
            "proposito_credito": form.proposito_credito.data,
            "monto_credito": form.monto_credito.data,
        }

        # Ejecutar motor de inferencia
        try:
            resultado = _engine.evaluate(datos_entrada)
        except Exception as e:
            logger.error("Error al evaluar: %s", e)
            flash(
                "Ocurrió un error al procesar la evaluación. "
                "Intenta de nuevo.",
                "danger",
            )
            return render_template("index.html", form=form)

        # Verificar errores de validación del motor
        errores = resultado.get("errores_validacion", [])
        if errores:
            for err in errores:
                flash(f"Error de validación: {err}", "warning")
            return render_template("index.html", form=form)

        # Guardar en base de datos
        try:
            evaluacion = Evaluacion.from_inference_result(
                datos_entrada, resultado
            )
            db.session.add(evaluacion)
            db.session.commit()
            logger.info(
                "Evaluación #%d guardada: %s (score=%d)",
                evaluacion.id,
                evaluacion.dictamen,
                evaluacion.score_final,
            )
        except Exception as e:
            db.session.rollback()
            logger.error("Error al guardar en BD: %s", e)
            flash(
                "Error al guardar la evaluación en la base "
                "de datos.",
                "danger",
            )
            return render_template("index.html", form=form)

        # Redirigir a página de resultado
        flash("Evaluación completada exitosamente.", "success")
        return redirect(
            url_for("main.resultado", eval_id=evaluacion.id)
        )

    return render_template("index.html", form=form)


# ════════════════════════════════════════════════════════════
# RUTA: RESULTADO DE EVALUACIÓN
# ════════════════════════════════════════════════════════════

@main.route("/resultado/<int:eval_id>")
def resultado(eval_id):
    """Muestra el resultado detallado de una evaluación."""
    from app.utils import clasificar_dti

    evaluacion = Evaluacion.query.get_or_404(eval_id)
    reglas = evaluacion.get_reglas_list()
    sub_scores = evaluacion.get_sub_scores_dict()
    dti_info = clasificar_dti(evaluacion.dti_ratio)

    # Preparar info de sub-scores para el template
    maximos = {
        "solvencia": 40,
        "estabilidad": 30,
        "historial_score": 20,
        "perfil": 10,
    }
    labels = {
        "solvencia": "Solvencia",
        "estabilidad": "Estabilidad",
        "historial_score": "Historial",
        "perfil": "Perfil",
    }
    sub_scores_info = {}
    for key, max_val in maximos.items():
        valor = sub_scores.get(key, 0)
        pct = (valor / max_val * 100) if max_val > 0 else 0
        sub_scores_info[key] = {
            "label": labels.get(key, key),
            "valor": valor,
            "max": max_val,
            "pct": round(pct, 1),
            "color": (
                "#10B981" if pct >= 60
                else "#F59E0B" if pct >= 30
                else "#EF4444"
            ),
        }

    return render_template(
        "resultado.html",
        ev=evaluacion,
        reglas=reglas,
        sub_scores_info=sub_scores_info,
        dti_info=dti_info,
    )


# ════════════════════════════════════════════════════════════
# RUTA: HISTORIAL DE EVALUACIONES
# ════════════════════════════════════════════════════════════

PER_PAGE = 15

@main.route("/historial")
def historial():
    """Historial paginado de evaluaciones con filtros."""
    # Parámetros de filtro
    filtro_dictamen = request.args.get("dictamen", "").strip()
    filtro_orden = request.args.get("orden", "reciente").strip()
    pagina = request.args.get("page", 1, type=int)

    # Query base
    query = Evaluacion.query

    # Filtro por dictamen
    if filtro_dictamen in ("APROBADO", "RECHAZADO", "REVISION_MANUAL"):
        query = query.filter(Evaluacion.dictamen == filtro_dictamen)

    # Ordenamiento
    orden_map = {
        "reciente": Evaluacion.timestamp.desc(),
        "antiguo": Evaluacion.timestamp.asc(),
        "score_alto": Evaluacion.score_final.desc(),
        "score_bajo": Evaluacion.score_final.asc(),
    }
    orden = orden_map.get(filtro_orden, Evaluacion.timestamp.desc())
    query = query.order_by(orden)

    # Contar total
    total = query.count()
    paginas = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    pagina = max(1, min(pagina, paginas))

    # Paginar
    evaluaciones = query.offset((pagina - 1) * PER_PAGE).limit(PER_PAGE).all()

    return render_template(
        "historial.html",
        evaluaciones=evaluaciones,
        total=total,
        pagina=pagina,
        paginas=paginas,
        filtro_dictamen=filtro_dictamen,
        filtro_orden=filtro_orden,
    )


# ════════════════════════════════════════════════════════════
# RUTA: DASHBOARD ANALÍTICO
# ════════════════════════════════════════════════════════════

@main.route("/dashboard")
def dashboard():
    """Dashboard con KPIs, gráficas y estadísticas agregadas."""
    from sqlalchemy import func
    import json

    # ── KPIs principales ────────────────────────────────────
    total = Evaluacion.query.count()

    if total == 0:
        return render_template("dashboard.html", vacio=True, total=0)

    aprobados = Evaluacion.query.filter_by(dictamen="APROBADO").count()
    rechazados = Evaluacion.query.filter_by(dictamen="RECHAZADO").count()
    revision = Evaluacion.query.filter_by(dictamen="REVISION_MANUAL").count()

    score_prom = db.session.query(func.avg(Evaluacion.score_final)).scalar() or 0
    dti_prom = db.session.query(func.avg(Evaluacion.dti_ratio)).scalar() or 0
    monto_total = db.session.query(func.sum(Evaluacion.monto_credito)).scalar() or 0

    tasa_aprobacion = (aprobados / total * 100) if total > 0 else 0

    kpis = {
        "total": total,
        "aprobados": aprobados,
        "rechazados": rechazados,
        "revision": revision,
        "score_promedio": round(score_prom, 1),
        "dti_promedio": round(dti_prom * 100, 1),
        "monto_total": round(monto_total, 2),
        "tasa_aprobacion": round(tasa_aprobacion, 1),
    }

    # ── Distribución de dictámenes (pie chart) ──────────────
    chart_dictamen = {
        "labels": ["Aprobado", "Revisión Manual", "Rechazado"],
        "data": [aprobados, revision, rechazados],
        "colors": ["#10B981", "#F59E0B", "#EF4444"],
    }

    # ── Distribución de scores (histograma) ─────────────────
    rangos = [
        ("0–19", 0, 19),
        ("20–39", 20, 39),
        ("40–59", 40, 59),
        ("60–79", 60, 79),
        ("80–100", 80, 100),
    ]
    hist_data = []
    hist_labels = []
    hist_colors = []
    color_map = {0: "#EF4444", 1: "#EF4444", 2: "#F59E0B", 3: "#F59E0B", 4: "#10B981"}
    for i, (label, lo, hi) in enumerate(rangos):
        count = Evaluacion.query.filter(
            Evaluacion.score_final >= lo,
            Evaluacion.score_final <= hi,
        ).count()
        hist_labels.append(label)
        hist_data.append(count)
        hist_colors.append(color_map[i])

    chart_scores = {
        "labels": hist_labels,
        "data": hist_data,
        "colors": hist_colors,
    }

    # ── Distribución por propósito (bar chart) ──────────────
    propositos_q = (
        db.session.query(
            Evaluacion.proposito_credito,
            func.count(Evaluacion.id),
        )
        .group_by(Evaluacion.proposito_credito)
        .order_by(func.count(Evaluacion.id).desc())
        .all()
    )
    chart_proposito = {
        "labels": [p[0] for p in propositos_q],
        "data": [p[1] for p in propositos_q],
    }

    # ── Distribución de DTI (categorías) ────────────────────
    dti_cats = [
        ("Bajo (<25%)", 0, 0.25),
        ("Moderado (25–40%)", 0.25, 0.40),
        ("Alto (40–60%)", 0.40, 0.60),
        ("Crítico (>60%)", 0.60, 10.0),
    ]
    dti_labels = []
    dti_data = []
    dti_colors = ["#10B981", "#F59E0B", "#FB923C", "#EF4444"]
    for label, lo, hi in dti_cats:
        count = Evaluacion.query.filter(
            Evaluacion.dti_ratio >= lo,
            Evaluacion.dti_ratio < hi,
        ).count()
        dti_labels.append(label)
        dti_data.append(count)

    chart_dti = {
        "labels": dti_labels,
        "data": dti_data,
        "colors": dti_colors,
    }

    # ── Últimas 5 evaluaciones ──────────────────────────────
    ultimas = (
        Evaluacion.query
        .order_by(Evaluacion.timestamp.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "dashboard.html",
        vacio=False,
        kpis=kpis,
        total=total,
        chart_dictamen=json.dumps(chart_dictamen),
        chart_scores=json.dumps(chart_scores),
        chart_proposito=json.dumps(chart_proposito),
        chart_dti=json.dumps(chart_dti),
        ultimas=ultimas,
    )


# ════════════════════════════════════════════════════════════
# RUTA: DESCARGAR PDF — REPORTE COMPLETO
# ════════════════════════════════════════════════════════════

@main.route("/resultado/<int:eval_id>/pdf")
def descargar_pdf(eval_id):
    """Genera y descarga el PDF completo (auditoría)."""
    evaluacion = Evaluacion.query.get_or_404(eval_id)
    datos = evaluacion.to_dict()
    output_path = (
        f"reports/exports/evaluacion_{eval_id}_completo.pdf"
    )
    try:
        pdf_path = _pdf_gen.generate_complete_report(
            datos, output_path
        )
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f"MIHAC_Evaluacion_{eval_id}.pdf",
        )
    except Exception as e:
        logger.error("Error generando PDF completo: %s", e)
        flash(
            "Error al generar el reporte PDF. Intenta de nuevo.",
            "danger",
        )
        return redirect(url_for("main.resultado", eval_id=eval_id))


# ════════════════════════════════════════════════════════════
# RUTA: DESCARGAR PDF — REPORTE CLIENTE
# ════════════════════════════════════════════════════════════

@main.route("/resultado/<int:eval_id>/pdf-cliente")
def descargar_pdf_cliente(eval_id):
    """Genera y descarga el PDF simplificado (cliente)."""
    evaluacion = Evaluacion.query.get_or_404(eval_id)
    datos = evaluacion.to_dict()
    output_path = (
        f"reports/exports/evaluacion_{eval_id}_cliente.pdf"
    )
    try:
        pdf_path = _pdf_gen.generate_client_report(
            datos, output_path
        )
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f"Resultado_Solicitud_{eval_id}.pdf",
        )
    except Exception as e:
        logger.error("Error generando PDF cliente: %s", e)
        flash(
            "Error al generar el reporte PDF. Intenta de nuevo.",
            "danger",
        )
        return redirect(url_for("main.resultado", eval_id=eval_id))


# ════════════════════════════════════════════════════════════
# RUTAS V2 — Rediseño visual (Módulo F)
# ════════════════════════════════════════════════════════════
# Activación: variable de entorno MIHAC_V2_UI=true
# Las rutas legacy (/, /resultado, /dashboard, /historial)
# continúan funcionando con Bootstrap 5.3 sin cambios.
# ════════════════════════════════════════════════════════════

# Motor calibrado MX (singleton). Si la env-var no está
# definida, se comporta idéntico al motor base.
_engine_mx = CalibratedEngine(thresholds_file="thresholds_mx.json")


def _v2_enabled() -> bool:
    """¿Está activado el rediseño visual?"""
    return os.environ.get("MIHAC_V2_UI", "").lower() in (
        "1", "true", "yes", "on",
    )


@main.before_request
def _block_v2_if_disabled():
    """Devuelve 404 para rutas /*_v2 si la flag no está activa."""
    if request.endpoint and request.endpoint.endswith("_v2"):
        if not _v2_enabled():
            from flask import abort
            abort(404)


@main.route("/dashboard_v2")
def dashboard_v2():
    """Dashboard v2 con cards + Chart.js."""
    ventana_dias = 30
    desde = datetime.utcnow() - timedelta(days=ventana_dias)
    evals = Evaluacion.query.filter(
        Evaluacion.timestamp >= desde
    ).all()
    total_all = Evaluacion.query.count()

    n = len(evals)
    apr = sum(1 for e in evals if e.dictamen == "APROBADO")
    rec = sum(1 for e in evals if e.dictamen == "RECHAZADO")
    rev = sum(1 for e in evals if e.dictamen == "REVISION_MANUAL")

    stats = {
        "n_evaluaciones": n,
        "tasa_aprobacion": round(apr / n * 100, 2) if n else 0.0,
        "score_promedio": (
            round(sum(e.score_final for e in evals) / n, 2)
            if n else 0.0
        ),
        "dti_promedio": (
            round(sum(e.dti_ratio for e in evals) / n, 4)
            if n else 0.0
        ),
        "distribucion": {
            "APROBADO": apr,
            "REVISION_MANUAL": rev,
            "RECHAZADO": rec,
        },
    }

    bucket: dict[str, int] = {}
    for ev in evals:
        key = (
            ev.timestamp.strftime("%d/%m") if ev.timestamp else "?"
        )
        bucket[key] = bucket.get(key, 0) + 1
    line_labels = sorted(
        bucket.keys(),
        key=lambda s: (
            datetime.strptime(s, "%d/%m") if s != "?"
            else datetime.min
        ),
    )
    line_values = [bucket[k] for k in line_labels]

    chart_data = {
        "line_labels": line_labels,
        "line_values": line_values,
    }

    ultimas = (
        Evaluacion.query
        .order_by(Evaluacion.id.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "dashboard_v2.html",
        stats=stats,
        ventana_dias=ventana_dias,
        chart_data=chart_data,
        ultimas=ultimas,
        total_evaluaciones=total_all,
    )


@main.route("/evaluate_v2", methods=["GET", "POST"])
def evaluate_v2():
    """Wizard de 3 pasos con UI v2 + soporte calibración MX."""
    if request.method == "POST":
        try:
            datos = {
                "edad": int(request.form["edad"]),
                "ingreso_mensual": float(
                    request.form["ingreso_mensual"]
                ),
                "total_deuda_actual": float(
                    request.form["total_deuda_actual"]
                ),
                "historial_crediticio": int(
                    request.form["historial_crediticio"]
                ),
                "antiguedad_laboral": int(
                    request.form["antiguedad_laboral"]
                ),
                "numero_dependientes": int(
                    request.form["numero_dependientes"]
                ),
                "tipo_vivienda": request.form["tipo_vivienda"],
                "proposito_credito": request.form[
                    "proposito_credito"
                ],
                "monto_credito": float(
                    request.form["monto_credito"]
                ),
            }
        except (KeyError, ValueError) as e:
            flash(f"Datos del formulario inválidos: {e}", "danger")
            return redirect(url_for("main.evaluate_v2"))

        usa_mx = bool(request.form.get("perfil_mx"))
        engine = _engine_mx if usa_mx else _engine

        resultado = engine.evaluate(datos)
        if resultado.get("errores_validacion"):
            for err in resultado["errores_validacion"]:
                flash(err, "danger")
            return redirect(url_for("main.evaluate_v2"))

        ev = Evaluacion.from_inference_result(datos, resultado)
        db.session.add(ev)
        db.session.commit()
        return redirect(
            url_for("main.result_v2", eval_id=ev.id)
        )

    return render_template(
        "evaluate_v2.html",
        form=None,
        total_evaluaciones=Evaluacion.query.count(),
    )


@main.route("/result_v2/<int:eval_id>")
def result_v2(eval_id: int):
    """Resultado v2 con gradiente + waterfall + radar Plotly."""
    ev = db.session.get(Evaluacion, eval_id)
    if ev is None:
        from flask import abort
        abort(404)

    resultado_dict = {
        "score_final": ev.score_final,
        "sub_scores": ev.get_sub_scores_dict(),
        "reglas_activadas": ev.get_reglas_list(),
    }
    charts = build_charts_for_template(resultado_dict)

    return render_template(
        "result_v2.html",
        ev=ev,
        charts=charts,
        total_evaluaciones=Evaluacion.query.count(),
    )


@main.route("/historial_v2")
def historial_v2():
    """Historial v2 con filtros y badges."""
    filtro_dictamen = request.args.get("dictamen") or ""
    q = Evaluacion.query.order_by(Evaluacion.id.desc())
    if filtro_dictamen:
        q = q.filter(Evaluacion.dictamen == filtro_dictamen)

    items = q.limit(100).all()
    total = q.count()
    return render_template(
        "historial_v2.html",
        items=items,
        total=total,
        filtro_dictamen=filtro_dictamen,
        total_evaluaciones=Evaluacion.query.count(),
    )
