# ============================================================
# MIHAC v2.0 — Tests de la API REST v2 (Módulo E)
# tests/test_api_v2.py
# ============================================================
# Cubre los 7 endpoints expuestos por app/api/v2.py:
#   POST /api/v2/evaluate            (con perfil v1 y mx)
#   POST /api/v2/evaluate/batch
#   GET  /api/v2/history
#   GET  /api/v2/monitoring/stats
#   GET  /api/v2/rules
#   GET  /api/v2/openapi.json
#   GET  /api/v2/docs
# ============================================================

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parent
_ROOT = _TESTS.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app import create_app, db


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture()
def client():
    """App Flask en modo testing con BD SQLite en memoria."""
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        with app.test_client() as c:
            yield c
        db.session.remove()
        db.drop_all()


CASO_IDEAL = {
    "edad": 35,
    "ingreso_mensual": 25000.0,
    "total_deuda_actual": 4000.0,
    "historial_crediticio": 2,
    "antiguedad_laboral": 7,
    "numero_dependientes": 1,
    "tipo_vivienda": "Propia",
    "proposito_credito": "Negocio",
    "monto_credito": 15000.0,
}


# ── /evaluate ────────────────────────────────────────────────

class TestEvaluateEndpoint:

    def test_caso_ideal_aprobado(self, client):
        resp = client.post(
            "/api/v2/evaluate",
            data=json.dumps(CASO_IDEAL),
            content_type="application/json",
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["dictamen"] == "APROBADO"
        assert body["score_final"] >= 80
        assert body["perfil_calibracion"] == "v1"
        assert body["request_id"].startswith("eval_")
        assert "tiempo_evaluacion_ms" in body
        assert body["evaluacion_id"] is not None

    def test_payload_vacio_400(self, client):
        resp = client.post(
            "/api/v2/evaluate",
            data="{}",
            content_type="application/json",
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert "errores_validacion" in body
        assert any("campo faltante" in e for e in body["errores_validacion"])

    def test_tipo_vivienda_invalido_400(self, client):
        bad = {**CASO_IDEAL, "tipo_vivienda": "Cueva"}
        resp = client.post(
            "/api/v2/evaluate",
            data=json.dumps(bad),
            content_type="application/json",
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert any(
            "tipo_vivienda" in e for e in body["errores_validacion"]
        )

    def test_perfil_mx_via_query(self, client):
        # Caso de zona gris: score 75-79 con monto $10K
        # con v1 → REVISION_MANUAL, con mx → APROBADO
        zona_gris = {
            **CASO_IDEAL,
            "monto_credito": 10000.0,
            "ingreso_mensual": 8000.0,
            "antiguedad_laboral": 2,
            "tipo_vivienda": "Familiar",
            "numero_dependientes": 2,
        }
        r1 = client.post(
            "/api/v2/evaluate?perfil=v1",
            data=json.dumps(zona_gris),
            content_type="application/json",
        ).get_json()
        r2 = client.post(
            "/api/v2/evaluate?perfil=mx",
            data=json.dumps(zona_gris),
            content_type="application/json",
        ).get_json()
        assert r1["perfil_calibracion"] == "v1"
        assert r2["perfil_calibracion"] == "mx"
        # El score debe ser idéntico (mismo motor de scoring)
        assert r1["score_final"] == r2["score_final"]

    def test_perfil_via_body(self, client):
        body = {**CASO_IDEAL, "perfil": "mx"}
        resp = client.post(
            "/api/v2/evaluate",
            data=json.dumps(body),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["perfil_calibracion"] == "mx"


# ── /evaluate/batch ──────────────────────────────────────────

class TestBatchEndpoint:

    def test_lote_pequeno_ok(self, client):
        body = {"solicitudes": [CASO_IDEAL] * 3}
        resp = client.post(
            "/api/v2/evaluate/batch",
            data=json.dumps(body),
            content_type="application/json",
        )
        assert resp.status_code == 200
        b = resp.get_json()
        assert b["n_total"] == 3
        assert b["distribucion_dictamenes"]["APROBADO"] == 3

    def test_lote_excede_limite_422(self, client):
        body = {"solicitudes": [CASO_IDEAL] * 101}
        resp = client.post(
            "/api/v2/evaluate/batch",
            data=json.dumps(body),
            content_type="application/json",
        )
        assert resp.status_code == 422

    def test_lote_falta_campo(self, client):
        resp = client.post(
            "/api/v2/evaluate/batch",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_item_invalido_no_aborta_lote(self, client):
        body = {"solicitudes": [
            CASO_IDEAL,
            {"edad": 35},  # incompleto
            CASO_IDEAL,
        ]}
        resp = client.post(
            "/api/v2/evaluate/batch",
            data=json.dumps(body),
            content_type="application/json",
        )
        assert resp.status_code == 200
        b = resp.get_json()
        assert b["n_total"] == 3
        # Solo 2 dictámenes APROBADO, 1 con errores
        items_con_err = [
            r for r in b["resultados"] if r.get("errores_validacion")
        ]
        assert len(items_con_err) == 1


# ── /history ─────────────────────────────────────────────────

class TestHistoryEndpoint:

    def test_history_vacio(self, client):
        resp = client.get("/api/v2/history")
        assert resp.status_code == 200
        b = resp.get_json()
        assert b["total"] == 0
        assert b["items"] == []

    def test_history_tras_evaluaciones(self, client):
        # Crear 3 evaluaciones primero
        for _ in range(3):
            client.post(
                "/api/v2/evaluate",
                data=json.dumps(CASO_IDEAL),
                content_type="application/json",
            )
        resp = client.get("/api/v2/history?per_page=5")
        b = resp.get_json()
        assert b["total"] == 3
        assert len(b["items"]) == 3
        assert all(it["dictamen"] == "APROBADO" for it in b["items"])

    def test_history_filtro_dictamen(self, client):
        # Una evaluación que sí aprueba
        client.post(
            "/api/v2/evaluate",
            data=json.dumps(CASO_IDEAL),
            content_type="application/json",
        )
        resp = client.get("/api/v2/history?dictamen=APROBADO")
        assert resp.status_code == 200
        assert resp.get_json()["total"] == 1
        # Filtro a un dictamen sin matches
        resp2 = client.get("/api/v2/history?dictamen=RECHAZADO")
        assert resp2.get_json()["total"] == 0


# ── /monitoring/stats ────────────────────────────────────────

class TestMonitoringEndpoint:

    def test_stats_sin_datos(self, client):
        resp = client.get("/api/v2/monitoring/stats")
        assert resp.status_code == 200
        b = resp.get_json()
        assert b["n_evaluaciones"] == 0
        assert b["tasa_aprobacion"] == 0.0

    def test_stats_con_datos(self, client):
        for _ in range(2):
            client.post(
                "/api/v2/evaluate",
                data=json.dumps(CASO_IDEAL),
                content_type="application/json",
            )
        resp = client.get("/api/v2/monitoring/stats?days=7")
        b = resp.get_json()
        assert b["n_evaluaciones"] == 2
        assert b["tasa_aprobacion"] == 100.0
        assert b["distribucion"]["APROBADO"] == 2


# ── /rules ───────────────────────────────────────────────────

class TestRulesEndpoint:

    def test_rules_v1(self, client):
        resp = client.get("/api/v2/rules?perfil=v1")
        assert resp.status_code == 200
        b = resp.get_json()
        assert b["perfil_calibracion"] == "v1"
        assert b["thresholds_file"] == "thresholds.json"
        assert "rules" in b
        assert len(b["rules"]["reglas"]) == 15

    def test_rules_mx(self, client):
        resp = client.get("/api/v2/rules?perfil=mx")
        b = resp.get_json()
        assert b["thresholds_file"] == "thresholds_mx.json"
        # Verificar que el JSON MX tiene los umbrales calibrados
        thr = b["thresholds"]
        assert thr["dictamen"]["APROBADO"]["score_minimo"] == 70


# ── /openapi.json y /docs ────────────────────────────────────

class TestSwaggerEndpoints:

    def test_openapi_spec(self, client):
        resp = client.get("/api/v2/openapi.json")
        assert resp.status_code == 200
        spec = resp.get_json()
        assert spec["openapi"].startswith("3.")
        assert spec["info"]["title"] == "MIHAC API v2"
        # Endpoints declarados
        assert "/api/v2/evaluate" in spec["paths"]
        assert "/api/v2/evaluate/batch" in spec["paths"]
        assert "/api/v2/history" in spec["paths"]
        assert "/api/v2/rules" in spec["paths"]

    def test_swagger_docs_html(self, client):
        resp = client.get("/api/v2/docs")
        assert resp.status_code == 200
        assert b"swagger-ui" in resp.data
        assert b"/api/v2/openapi.json" in resp.data
