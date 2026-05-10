# ============================================================
# MIHAC v1.0 — Application Factory (Flask)
# app/__init__.py
# ============================================================
# Patrón Application Factory: permite crear múltiples
# instancias de la app con distinta configuración
# (development, testing, production).
#
# Ventajas:
#   1. Evita imports circulares al diferir init de extensiones
#   2. Cada test puede usar una app limpia con BD separada
#   3. Un solo código, múltiples entornos
# ============================================================

import sys
from pathlib import Path

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# ── Asegurar que mihac/ esté en sys.path ────────────────────
_APP_DIR = Path(__file__).resolve().parent
_MIHAC_ROOT = _APP_DIR.parent
if str(_MIHAC_ROOT) not in sys.path:
    sys.path.insert(0, str(_MIHAC_ROOT))

# ── Extensiones (sin app todavía) ───────────────────────────
db = SQLAlchemy()
migrate = Migrate()


def create_app(config_name: str = "development") -> Flask:
    """Crea y configura una instancia de la aplicación Flask.

    Args:
        config_name: Nombre del entorno de configuración.
            Opciones: 'development', 'testing', 'production'.

    Returns:
        Instancia de Flask configurada y lista para ejecutar.
    """
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )

    # ── Cargar configuración ────────────────────────────────
    from app.config import config_map
    cfg = config_map.get(config_name, config_map["development"])
    app.config.from_object(cfg)

    # ── Inicializar extensiones ─────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)

    # ── Registrar blueprints ────────────────────────────────
    from app.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    # API REST v2 (Módulo E)
    from app.api.v2 import bp as api_v2_blueprint
    app.register_blueprint(api_v2_blueprint)

    # ── Registrar error handlers ────────────────────────────
    _register_error_handlers(app)

    # ── Registrar filtros Jinja personalizados ──────────────
    _register_template_filters(app)

    # ── Crear tablas si no existen ──────────────────────────
    with app.app_context():
        from app import models  # noqa: F401
        db.create_all()

    return app


def _register_error_handlers(app: Flask) -> None:
    """Registra páginas de error personalizadas."""
    from flask import render_template

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500


def _register_template_filters(app: Flask) -> None:
    """Registra filtros Jinja2 personalizados."""
    from app.utils import (
        color_dictamen,
        clase_badge_dictamen,
        formato_moneda,
        formato_porcentaje,
        texto_historial,
    )

    app.jinja_env.filters["color_dictamen"] = color_dictamen
    app.jinja_env.filters["clase_badge"] = clase_badge_dictamen
    app.jinja_env.filters["moneda"] = formato_moneda
    app.jinja_env.filters["porcentaje"] = formato_porcentaje
    app.jinja_env.filters["texto_historial"] = texto_historial
