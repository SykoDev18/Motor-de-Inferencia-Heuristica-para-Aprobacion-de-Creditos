# ============================================================
# MIHAC v2.0 — Smoke tests del rediseño visual (Módulo F)
# tests/test_ui_v2.py
# ============================================================
# Verifica que las 4 rutas v2 responden 200 con la flag
# MIHAC_V2_UI=true y devuelven 404 cuando no está activada.
# Solo chequea HTML básico (presencia de marcadores), no
# renderizado JS.
# ============================================================

import os
import sys
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parent
_ROOT = _TESTS.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app import db
from app.models import Evaluacion
from core.engine import InferenceEngine


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


@pytest.fixture()
def client_v2(app):
    """Cliente de prueba con MIHAC_V2_UI=true.

    Reutiliza el fixture session-scoped `app` del conftest.py
    para no crear apps paralelas que tocan la misma BD en
    memoria. try/finally garantiza limpieza de la env var
    incluso si el test crashea.
    """
    prev = os.environ.get("MIHAC_V2_UI")
    os.environ["MIHAC_V2_UI"] = "true"
    try:
        # Limpieza de la tabla antes de cada test (no drop_all)
        with app.app_context():
            Evaluacion.query.delete()
            db.session.commit()
            yield app.test_client()
    finally:
        if prev is None:
            os.environ.pop("MIHAC_V2_UI", None)
        else:
            os.environ["MIHAC_V2_UI"] = prev


@pytest.fixture()
def client_v2_disabled(app):
    """Cliente sin la flag — las rutas v2 deben dar 404."""
    prev = os.environ.pop("MIHAC_V2_UI", None)
    try:
        yield app.test_client()
    finally:
        if prev is not None:
            os.environ["MIHAC_V2_UI"] = prev


# ── Flag de activación ───────────────────────────────────────

class TestFlagV2:

    def test_dashboard_v2_404_sin_flag(self, client_v2_disabled):
        resp = client_v2_disabled.get("/dashboard_v2")
        assert resp.status_code == 404

    def test_evaluate_v2_404_sin_flag(self, client_v2_disabled):
        resp = client_v2_disabled.get("/evaluate_v2")
        assert resp.status_code == 404

    def test_dashboard_v2_200_con_flag(self, client_v2):
        resp = client_v2.get("/dashboard_v2")
        assert resp.status_code == 200


# ── Rutas v2 con flag activa ─────────────────────────────────

class TestRutasV2:

    def test_dashboard_renderiza_marcadores(self, client_v2):
        resp = client_v2.get("/dashboard_v2")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        # Marcadores del rediseño
        assert "tailwindcss.com" in body
        assert "Lexend" in body
        assert "Inter" in body
        assert "chartLine" in body
        assert "chartDonut" in body

    def test_evaluate_v2_wizard_marcadores(self, client_v2):
        resp = client_v2.get("/evaluate_v2")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "wizardData" in body          # Alpine component
        assert "tipo_vivienda" in body       # campo de paso 1
        assert "ingreso_mensual" in body     # campo de paso 2
        assert "antiguedad_laboral" in body  # campo de paso 3

    def test_evaluate_v2_post_crea_evaluacion(self, client_v2):
        # POST con datos válidos → redirige a result_v2/<id>
        resp = client_v2.post(
            "/evaluate_v2",
            data=CASO_IDEAL,
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/result_v2/" in resp.headers["Location"]

    def test_result_v2_renderiza_charts(self, client_v2):
        # Crear una evaluación primero (vía la API v2 ya cubierta)
        with client_v2.application.app_context():
            engine = InferenceEngine()
            r = engine.evaluate(CASO_IDEAL)
            ev = Evaluacion.from_inference_result(CASO_IDEAL, r)
            db.session.add(ev)
            db.session.commit()
            ev_id = ev.id

        resp = client_v2.get(f"/result_v2/{ev_id}")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        # Marcadores de los charts Plotly
        assert "Plotly.newPlot" in body
        assert 'id="waterfall"' in body
        assert 'id="radar"' in body
        # Header con dictamen
        assert "score-reveal" in body
        assert "progress-fill" in body

    def test_result_v2_404(self, client_v2):
        resp = client_v2.get("/result_v2/999999")
        assert resp.status_code == 404

    def test_historial_v2_vacio(self, client_v2):
        resp = client_v2.get("/historial_v2")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "Sin evaluaciones" in body or "0 resultados" in body

    def test_historial_v2_con_filtro(self, client_v2):
        with client_v2.application.app_context():
            engine = InferenceEngine()
            r = engine.evaluate(CASO_IDEAL)
            ev = Evaluacion.from_inference_result(CASO_IDEAL, r)
            db.session.add(ev)
            db.session.commit()

        resp = client_v2.get("/historial_v2?dictamen=APROBADO")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "Aprobado" in body  # badge visible


# ── Rutas legacy siguen funcionando con flag activa ──────────

class TestLegacyConFlag:

    def test_index_v1_sigue_disponible(self, client_v2):
        resp = client_v2.get("/")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        # Legacy usa Bootstrap, no Tailwind
        assert "bootstrap" in body.lower()

    def test_dashboard_v1_sigue_disponible(self, client_v2):
        resp = client_v2.get("/dashboard")
        assert resp.status_code == 200
