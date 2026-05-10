# ============================================================
# MIHAC v2.0 — API REST v2 (Módulo E)
# app/api/v2.py
# ============================================================
# Endpoints JSON sobre el motor MIHAC, con soporte de
# calibración MX vía CalibratedEngine y especificación
# OpenAPI 3.0 + Swagger UI.
#
# Endpoints:
#   POST /api/v2/evaluate              — evaluación individual
#   POST /api/v2/evaluate/batch        — lote (≤100 solicitudes)
#   GET  /api/v2/history               — historial paginado
#   GET  /api/v2/monitoring/stats      — agregados 30 días
#   GET  /api/v2/rules                 — rules.json + thresholds
#   GET  /api/v2/openapi.json          — spec OpenAPI 3.0
#   GET  /api/v2/docs                  — Swagger UI (CDN)
#
# Convención:
#   - Errores 400: payload mal formado o validación falla
#   - Errores 422: límite de batch excedido o reglas de negocio
#   - Errores 500: capturados, devuelven {"error": "..."} (raros)
#
# Calibración MX:
#   El campo opcional `perfil` ∈ {"v1", "mx"} en el payload
#   selecciona el motor base (v1) o calibrado (mx) por
#   request. Default: "v1".
# ============================================================

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from app import db
from app.models import Evaluacion
from core.calibrated_engine import CalibratedEngine
from core.engine import InferenceEngine

logger = logging.getLogger(__name__)

bp = Blueprint(
    "api_v2",
    __name__,
    url_prefix="/api/v2",
    template_folder="templates",
)

# ── Singletons del motor por perfil ──────────────────────────

# El motor base v1.0 (sin override). Mismo objeto que /routes.py.
_engine_v1 = InferenceEngine()

# El motor calibrado MX (lee thresholds_mx.json explícitamente).
_engine_mx = CalibratedEngine(thresholds_file="thresholds_mx.json")

_ENGINES = {"v1": _engine_v1, "mx": _engine_mx}

# Límite de payload por lote
_BATCH_MAX = 100

# Versión semántica del motor expuesta por la API
_API_VERSION = "2.0.0"

# Conjuntos válidos para validación rápida (mismo contrato que validator)
_VALID_VIVIENDA = {"Propia", "Familiar", "Rentada"}
_VALID_PROPOSITO = {
    "Negocio", "Educacion", "Consumo",
    "Emergencia", "Vacaciones",
}
_REQUIRED_FIELDS = (
    "edad", "ingreso_mensual", "total_deuda_actual",
    "historial_crediticio", "antiguedad_laboral",
    "numero_dependientes", "tipo_vivienda",
    "proposito_credito", "monto_credito",
)


# ── Helpers ──────────────────────────────────────────────────

def _select_engine(perfil_query: str | None, payload: dict) -> tuple:
    """Devuelve (perfil, engine) según prioridad.

    Prioridad: ?perfil= en query string > campo "perfil" en
    payload > default "v1".
    """
    perfil = (
        perfil_query
        or payload.get("perfil")
        or "v1"
    ).lower()
    if perfil not in _ENGINES:
        perfil = "v1"
    return perfil, _ENGINES[perfil]


def _validate_payload(datos: dict) -> list[str]:
    """Validación ligera previa al engine (para 400 inmediato).

    Replica los chequeos básicos del Validator de v1.0 sin
    instanciarlo: tipos, rangos y conjuntos categóricos.
    """
    errs: list[str] = []
    for f in _REQUIRED_FIELDS:
        if f not in datos:
            errs.append(f"campo faltante: {f}")
    if errs:
        return errs

    # Tipos numéricos
    for f in (
        "ingreso_mensual", "total_deuda_actual", "monto_credito",
    ):
        if not isinstance(datos[f], (int, float)):
            errs.append(f"{f} debe ser numérico")
    for f in (
        "edad", "historial_crediticio",
        "antiguedad_laboral", "numero_dependientes",
    ):
        if not isinstance(datos[f], int):
            errs.append(f"{f} debe ser entero")

    # Conjuntos categóricos
    if datos.get("tipo_vivienda") not in _VALID_VIVIENDA:
        errs.append(
            f"tipo_vivienda inválido — usar {sorted(_VALID_VIVIENDA)}"
        )
    if datos.get("proposito_credito") not in _VALID_PROPOSITO:
        errs.append(
            f"proposito_credito inválido — usar {sorted(_VALID_PROPOSITO)}"
        )

    return errs


def _persist_evaluation(
    datos: dict, resultado: dict
) -> int | None:
    """Guarda la evaluación en SQLite y devuelve el ID. None si falla."""
    try:
        ev = Evaluacion.from_inference_result(datos, resultado)
        db.session.add(ev)
        db.session.commit()
        return int(ev.id)
    except Exception as e:  # pragma: no cover (defensive)
        logger.warning("No se pudo persistir evaluación: %s", e)
        db.session.rollback()
        return None


def _evaluate_one(perfil: str, engine, datos: dict) -> dict:
    """Corre el motor + persiste + arma respuesta enriquecida."""
    request_id = "eval_" + uuid.uuid4().hex[:12]
    t0 = time.perf_counter()
    resultado = engine.evaluate(datos)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)

    ev_id = _persist_evaluation(datos, resultado)

    body = {
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "perfil_calibracion": perfil,
        "umbrales_activos": resultado.get(
            "umbrales_activos",
            "(hardcoded v1.0)" if perfil == "v1" else None,
        ),
        "evaluacion_id": ev_id,
        "tiempo_evaluacion_ms": elapsed_ms,
        "version_motor": _API_VERSION,
        # Campos del motor
        "dictamen": resultado.get("dictamen"),
        "score_final": resultado.get("score_final"),
        "dti_ratio": resultado.get("dti_ratio"),
        "dti_clasificacion": resultado.get("dti_clasificacion"),
        "umbral_aplicado": resultado.get("umbral_aplicado"),
        "sub_scores": resultado.get("sub_scores"),
        "reglas_activadas": resultado.get("reglas_activadas", []),
        "compensaciones": resultado.get("compensaciones", []),
        "reporte_explicacion": resultado.get(
            "reporte_explicacion", ""
        ),
        "errores_validacion": resultado.get(
            "errores_validacion", []
        ),
    }
    return body


# ── POST /api/v2/evaluate ────────────────────────────────────

@bp.route("/evaluate", methods=["POST"])
def evaluate():
    """Evalúa una solicitud crediticia individual.

    Body JSON: las 9 variables MIHAC + opcionalmente "perfil".
    Query    : ?perfil=mx para activar thresholds_mx.json.
    """
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return (
            jsonify({"error": "body debe ser un objeto JSON"}),
            400,
        )

    errs = _validate_payload(payload)
    if errs:
        return (
            jsonify({"errores_validacion": errs}),
            400,
        )

    perfil, engine = _select_engine(
        request.args.get("perfil"), payload
    )
    # Limpiar el campo "perfil" antes de pasar al engine
    datos = {k: v for k, v in payload.items() if k != "perfil"}
    body = _evaluate_one(perfil, engine, datos)

    if body.get("errores_validacion"):
        return jsonify(body), 400
    return jsonify(body), 200


# ── POST /api/v2/evaluate/batch ──────────────────────────────

@bp.route("/evaluate/batch", methods=["POST"])
def evaluate_batch():
    """Evalúa una lista de hasta 100 solicitudes.

    Body JSON:
        {"solicitudes": [...], "perfil": "v1"|"mx"}
    """
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict) or "solicitudes" not in payload:
        return (
            jsonify({
                "error": "body debe contener 'solicitudes': lista"
            }),
            400,
        )

    lista = payload.get("solicitudes")
    if not isinstance(lista, list):
        return (
            jsonify({"error": "'solicitudes' debe ser lista"}),
            400,
        )
    if len(lista) > _BATCH_MAX:
        return (
            jsonify({
                "error": (
                    f"Tamaño de lote excede {_BATCH_MAX}: "
                    f"recibido {len(lista)}"
                )
            }),
            422,
        )

    perfil, engine = _select_engine(
        request.args.get("perfil"), payload
    )

    resultados: list[dict] = []
    counts = {"APROBADO": 0, "REVISION_MANUAL": 0, "RECHAZADO": 0}
    for i, item in enumerate(lista):
        if not isinstance(item, dict):
            resultados.append({
                "indice": i,
                "errores_validacion": ["item no es objeto JSON"],
            })
            continue

        errs = _validate_payload(item)
        if errs:
            resultados.append({
                "indice": i,
                "errores_validacion": errs,
            })
            continue

        datos = {k: v for k, v in item.items() if k != "perfil"}
        r = _evaluate_one(perfil, engine, datos)
        r["indice"] = i
        resultados.append(r)
        d = r.get("dictamen")
        if d in counts:
            counts[d] += 1

    return jsonify({
        "perfil_calibracion": perfil,
        "n_total": len(lista),
        "distribucion_dictamenes": counts,
        "resultados": resultados,
    }), 200


# ── GET /api/v2/history ──────────────────────────────────────

@bp.route("/history", methods=["GET"])
def history():
    """Devuelve evaluaciones previas con paginación.

    Query:
        page    (int, default=1)
        per_page (int, default=20, max=100)
        dictamen (str, opcional, filtra por valor exacto)
    """
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(
            100, max(1, int(request.args.get("per_page", 20)))
        )
    except (TypeError, ValueError):
        return (
            jsonify({"error": "page/per_page deben ser enteros"}),
            400,
        )

    dictamen_filter = request.args.get("dictamen")
    q = Evaluacion.query.order_by(Evaluacion.id.desc())
    if dictamen_filter:
        q = q.filter(Evaluacion.dictamen == dictamen_filter)

    total = q.count()
    items = (
        q.limit(per_page)
        .offset((page - 1) * per_page)
        .all()
    )

    return jsonify({
        "page": page,
        "per_page": per_page,
        "total": total,
        "n_paginas": (total + per_page - 1) // per_page,
        "items": [
            {
                "id": ev.id,
                "timestamp": (
                    ev.timestamp.isoformat()
                    if ev.timestamp else None
                ),
                "dictamen": ev.dictamen,
                "score_final": ev.score_final,
                "dti_ratio": ev.dti_ratio,
                "dti_clasificacion": ev.dti_clasificacion,
                "monto_credito": ev.monto_credito,
                "proposito_credito": ev.proposito_credito,
            }
            for ev in items
        ],
    }), 200


# ── GET /api/v2/monitoring/stats ─────────────────────────────

@bp.route("/monitoring/stats", methods=["GET"])
def monitoring_stats():
    """Agregados de los últimos 30 días.

    Query:
        days (int, default=30, max=365)
    """
    try:
        days = min(
            365, max(1, int(request.args.get("days", 30)))
        )
    except (TypeError, ValueError):
        days = 30

    since = datetime.utcnow() - timedelta(days=days)
    q = Evaluacion.query.filter(
        Evaluacion.timestamp >= since
    )
    items = q.all()

    n = len(items)
    if n == 0:
        return jsonify({
            "ventana_dias": days,
            "n_evaluaciones": 0,
            "tasa_aprobacion": 0.0,
            "score_promedio": 0.0,
            "dti_promedio": 0.0,
            "distribucion": {},
        }), 200

    apr = sum(1 for e in items if e.dictamen == "APROBADO")
    rec = sum(1 for e in items if e.dictamen == "RECHAZADO")
    rev = sum(
        1 for e in items if e.dictamen == "REVISION_MANUAL"
    )

    return jsonify({
        "ventana_dias": days,
        "n_evaluaciones": n,
        "tasa_aprobacion": round(apr / n * 100, 2),
        "tasa_rechazo": round(rec / n * 100, 2),
        "tasa_revision": round(rev / n * 100, 2),
        "score_promedio": round(
            sum(e.score_final for e in items) / n, 2
        ),
        "dti_promedio": round(
            sum(e.dti_ratio for e in items) / n, 4
        ),
        "distribucion": {
            "APROBADO": apr,
            "REVISION_MANUAL": rev,
            "RECHAZADO": rec,
        },
    }), 200


# ── GET /api/v2/rules ────────────────────────────────────────

@bp.route("/rules", methods=["GET"])
def rules():
    """Devuelve las 15 reglas + el archivo de umbrales activo.

    Query:
        perfil ∈ {v1, mx}  default v1
    """
    perfil = request.args.get("perfil", "v1").lower()
    knowledge_dir = Path(__file__).resolve().parent.parent.parent / "knowledge"

    try:
        rules_data = json.loads(
            (knowledge_dir / "rules.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as e:
        return (
            jsonify({"error": f"no se pudo leer rules.json: {e}"}),
            500,
        )

    thr_file = (
        "thresholds_mx.json" if perfil == "mx" else "thresholds.json"
    )
    try:
        thr_data = json.loads(
            (knowledge_dir / thr_file).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        thr_data = None

    return jsonify({
        "perfil_calibracion": perfil,
        "thresholds_file": thr_file,
        "thresholds": thr_data,
        "rules": rules_data,
    }), 200


# ── GET /api/v2/openapi.json ─────────────────────────────────

def _build_openapi_spec() -> dict:
    """Genera la especificación OpenAPI 3.0 del API v2."""
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "MIHAC API v2",
            "description": (
                "Motor de Inferencia Heurística para "
                "Aprobación de Créditos. API REST con "
                "soporte de calibración mexicana."
            ),
            "version": _API_VERSION,
            "contact": {
                "name": "Proyecto MIHAC — Tesis UAEH-EST",
            },
        },
        "servers": [
            {"url": "http://localhost:5000",
             "description": "Local development"},
        ],
        "tags": [
            {"name": "Evaluación",
             "description": "Endpoints de inferencia"},
            {"name": "Historial",
             "description": "Consulta de evaluaciones previas"},
            {"name": "Monitoreo",
             "description": "Agregados y métricas"},
            {"name": "Configuración",
             "description": "Reglas y umbrales activos"},
        ],
        "components": {
            "schemas": {
                "Solicitud": {
                    "type": "object",
                    "required": list(_REQUIRED_FIELDS),
                    "properties": {
                        "edad": {
                            "type": "integer", "minimum": 18,
                            "maximum": 99, "example": 35,
                        },
                        "ingreso_mensual": {
                            "type": "number", "format": "float",
                            "minimum": 0.01, "example": 25000.0,
                        },
                        "total_deuda_actual": {
                            "type": "number", "format": "float",
                            "minimum": 0, "example": 4000.0,
                        },
                        "historial_crediticio": {
                            "type": "integer", "enum": [0, 1, 2],
                            "description": "0=Malo, 1=Neutro, 2=Bueno",
                            "example": 2,
                        },
                        "antiguedad_laboral": {
                            "type": "integer", "minimum": 0,
                            "maximum": 40, "example": 7,
                        },
                        "numero_dependientes": {
                            "type": "integer", "minimum": 0,
                            "maximum": 10, "example": 1,
                        },
                        "tipo_vivienda": {
                            "type": "string",
                            "enum": sorted(_VALID_VIVIENDA),
                            "example": "Propia",
                        },
                        "proposito_credito": {
                            "type": "string",
                            "enum": sorted(_VALID_PROPOSITO),
                            "example": "Negocio",
                        },
                        "monto_credito": {
                            "type": "number", "format": "float",
                            "minimum": 500, "maximum": 50000,
                            "example": 15000.0,
                        },
                        "perfil": {
                            "type": "string",
                            "enum": ["v1", "mx"],
                            "default": "v1",
                            "description": (
                                "Activa thresholds_mx.json "
                                "(calibración México)."
                            ),
                        },
                    },
                },
                "Resultado": {
                    "type": "object",
                    "properties": {
                        "request_id": {"type": "string"},
                        "dictamen": {
                            "type": "string",
                            "enum": [
                                "APROBADO",
                                "REVISION_MANUAL",
                                "RECHAZADO",
                            ],
                        },
                        "score_final": {
                            "type": "integer", "minimum": 0,
                            "maximum": 100,
                        },
                        "dti_ratio": {"type": "number"},
                        "dti_clasificacion": {"type": "string"},
                        "perfil_calibracion": {"type": "string"},
                        "umbrales_activos": {"type": "string"},
                        "tiempo_evaluacion_ms": {"type": "number"},
                        "evaluacion_id": {"type": "integer"},
                        "version_motor": {"type": "string"},
                    },
                },
                "Error400": {
                    "type": "object",
                    "properties": {
                        "errores_validacion": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
        "paths": {
            "/api/v2/evaluate": {
                "post": {
                    "tags": ["Evaluación"],
                    "summary": "Evaluar una solicitud individual",
                    "parameters": [
                        {
                            "in": "query", "name": "perfil",
                            "schema": {
                                "type": "string",
                                "enum": ["v1", "mx"],
                            },
                            "required": False,
                        },
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": (
                                        "#/components/schemas/"
                                        "Solicitud"
                                    )
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Evaluación exitosa",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": (
                                            "#/components/"
                                            "schemas/Resultado"
                                        )
                                    }
                                }
                            },
                        },
                        "400": {
                            "description": "Validación fallida",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": (
                                            "#/components/"
                                            "schemas/Error400"
                                        )
                                    }
                                }
                            },
                        },
                    },
                },
            },
            "/api/v2/evaluate/batch": {
                "post": {
                    "tags": ["Evaluación"],
                    "summary": (
                        f"Evaluar hasta {_BATCH_MAX} "
                        "solicitudes en lote"
                    ),
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["solicitudes"],
                                    "properties": {
                                        "perfil": {
                                            "type": "string",
                                            "enum": ["v1", "mx"],
                                        },
                                        "solicitudes": {
                                            "type": "array",
                                            "maxItems": _BATCH_MAX,
                                            "items": {
                                                "$ref": (
                                                    "#/components/"
                                                    "schemas/"
                                                    "Solicitud"
                                                )
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Lote procesado"},
                        "422": {
                            "description": "Lote excede límite",
                        },
                    },
                },
            },
            "/api/v2/history": {
                "get": {
                    "tags": ["Historial"],
                    "summary": "Listar evaluaciones previas",
                    "parameters": [
                        {
                            "in": "query", "name": "page",
                            "schema": {
                                "type": "integer", "default": 1
                            },
                        },
                        {
                            "in": "query", "name": "per_page",
                            "schema": {
                                "type": "integer", "default": 20,
                                "maximum": 100,
                            },
                        },
                        {
                            "in": "query", "name": "dictamen",
                            "schema": {
                                "type": "string",
                                "enum": [
                                    "APROBADO",
                                    "REVISION_MANUAL",
                                    "RECHAZADO",
                                ],
                            },
                        },
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
            },
            "/api/v2/monitoring/stats": {
                "get": {
                    "tags": ["Monitoreo"],
                    "summary": (
                        "Agregados de los últimos N días"
                    ),
                    "parameters": [
                        {
                            "in": "query", "name": "days",
                            "schema": {
                                "type": "integer", "default": 30,
                                "maximum": 365,
                            },
                        },
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
            },
            "/api/v2/rules": {
                "get": {
                    "tags": ["Configuración"],
                    "summary": (
                        "Reglas + umbrales activos del perfil"
                    ),
                    "parameters": [
                        {
                            "in": "query", "name": "perfil",
                            "schema": {
                                "type": "string",
                                "enum": ["v1", "mx"],
                                "default": "v1",
                            },
                        },
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
            },
        },
    }


_OPENAPI_SPEC = _build_openapi_spec()


@bp.route("/openapi.json", methods=["GET"])
def openapi_json():
    """Devuelve la especificación OpenAPI 3.0 del API v2."""
    return jsonify(_OPENAPI_SPEC), 200


# ── GET /api/v2/docs (Swagger UI vía CDN) ────────────────────

_SWAGGER_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>MIHAC API v2 — Swagger UI</title>
    <link rel="stylesheet" type="text/css"
          href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
    <style>html{box-sizing:border-box;overflow:-moz-scrollbars-vertical;
        overflow-y:scroll}*,*:before,*:after{box-sizing:inherit}
        body{margin:0;background:#fafafa}</style>
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
window.onload = function() {
    SwaggerUIBundle({
        url: "/api/v2/openapi.json",
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [SwaggerUIBundle.presets.apis],
        layout: "BaseLayout",
    });
};
</script>
</body>
</html>"""


@bp.route("/docs", methods=["GET"])
def swagger_docs():
    """Sirve Swagger UI consumiendo /api/v2/openapi.json."""
    return _SWAGGER_HTML, 200, {"Content-Type": "text/html"}
