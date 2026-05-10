# ============================================================
# MIHAC v2.0 — Motor con umbrales calibrables (Módulo G+)
# core/calibrated_engine.py
# ============================================================
# Subclase de InferenceEngine que activa los umbrales del
# archivo apuntado por la variable de entorno
# `MIHAC_THRESHOLDS_FILE` (relativa a knowledge/).
#
# Diseño deliberadamente NO invasivo:
#   - InferenceEngine v1.0 queda intacto: sus 254 tests no se
#     ven afectados.
#   - CalibratedEngine corre el motor base con sus umbrales
#     hardcodeados y luego REINTERPRETA `score_final + dti +
#     monto` aplicando los umbrales del JSON activo.
#   - Si la variable de entorno no está definida, el
#     comportamiento es idéntico al de InferenceEngine.
#
# Esto reproduce el A/B del Módulo G de forma transparente y
# permite que la API REST v2 (Módulo E) ofrezca un parámetro
# `?perfil=mx` o header equivalente sin recompilar el motor
# de reglas.
#
# Uso::
#
#   import os
#   os.environ["MIHAC_THRESHOLDS_FILE"] = "thresholds_mx.json"
#   from core.calibrated_engine import CalibratedEngine
#   engine = CalibratedEngine()
#   res = engine.evaluate(datos)  # dictamen recalibrado
# ============================================================

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Asegurar import desde la raíz del proyecto (mismo patrón que core/engine.py)
_CORE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CORE_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.engine import InferenceEngine  # noqa: E402

logger = logging.getLogger(__name__)

_KNOWLEDGE_DIR = _PROJECT_ROOT / "knowledge"

_ENV_VAR = "MIHAC_THRESHOLDS_FILE"


class CalibratedEngine(InferenceEngine):
    """Motor con umbrales reemplazables vía variable de entorno.

    Hereda toda la lógica de InferenceEngine y añade un paso
    final que reinterpreta `score_final` con los umbrales del
    archivo JSON apuntado por `MIHAC_THRESHOLDS_FILE`.

    Si la variable está vacía o el archivo no existe, se
    comporta exactamente como InferenceEngine.

    Ejemplo::

        os.environ["MIHAC_THRESHOLDS_FILE"] = "thresholds_mx.json"
        engine = CalibratedEngine()
        res = engine.evaluate(datos)
    """

    def __init__(
        self,
        thresholds_file: str | None = None,
    ) -> None:
        """Inicializa el motor con umbrales opcionales.

        Args:
            thresholds_file: Nombre del JSON dentro de
                `knowledge/`. Si es None, se lee de
                `MIHAC_THRESHOLDS_FILE`. Si esa también está
                vacía, no se aplica ninguna recalibración.
        """
        super().__init__()
        self._thresholds: dict[str, Any] | None = None
        self._thresholds_source: str | None = None
        self._load_thresholds(thresholds_file)

    # ────────────────────────────────────────────────────────
    # CARGA DE UMBRALES
    # ────────────────────────────────────────────────────────

    def _load_thresholds(self, override: str | None) -> None:
        """Carga el archivo de umbrales si está configurado."""
        filename = override or os.environ.get(_ENV_VAR)
        if not filename:
            logger.debug(
                "Sin override de umbrales — comportamiento "
                "idéntico a InferenceEngine."
            )
            return

        path = _KNOWLEDGE_DIR / filename
        if not path.exists():
            logger.warning(
                "MIHAC_THRESHOLDS_FILE=%s no encontrado en %s. "
                "Se usa el motor base.",
                filename, _KNOWLEDGE_DIR,
            )
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                self._thresholds = json.load(f)
            self._thresholds_source = filename
            logger.info(
                "CalibratedEngine activo con %s", filename
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.error(
                "Error cargando %s: %s. Se usa motor base.",
                path, e,
            )
            self._thresholds = None

    # ────────────────────────────────────────────────────────
    # EVALUACIÓN CON RECALIBRACIÓN POST-EVAL
    # ────────────────────────────────────────────────────────

    def evaluate(self, datos: dict) -> dict:
        """Evalúa con el motor base y recalibra el dictamen."""
        result = super().evaluate(datos)

        # Si hay errores de validación, no recalibrar
        if result.get("errores_validacion"):
            return result
        if self._thresholds is None:
            return result

        # Recalibrar dictamen usando umbrales del JSON activo
        result["dictamen"] = self._recalibrate_dictamen(
            score=int(result["score_final"]),
            monto=float(datos.get("monto_credito", 0.0)),
            dti_clasif=str(result.get("dti_clasificacion", "")),
        )

        # Anotar metadatos de calibración para auditoría
        result["umbrales_activos"] = self._thresholds_source

        return result

    def _recalibrate_dictamen(
        self,
        score: int,
        monto: float,
        dti_clasif: str,
    ) -> str:
        """Reaplica los umbrales del JSON para producir dictamen.

        Lógica:
          1. DTI CRITICO mantiene siempre el veto → RECHAZADO.
          2. Calcula umbral_aprobado = base + ajuste_por_monto.
          3. Calcula umbral_revision = umbral_aprobado − 20 si
             el JSON usa banda relativa, o el valor absoluto
             score_revision_floor si el JSON lo provee.
          4. APROBADO si score ≥ umbral_aprobado.
             REVISION_MANUAL si umbral_revision ≤ score < umbral_aprobado.
             RECHAZADO en otro caso.
        """
        if dti_clasif == "CRITICO":
            return "RECHAZADO"

        thr = self._thresholds or {}
        dictamen_cfg = thr.get("dictamen", {})
        aprob = dictamen_cfg.get("APROBADO", {})
        rechaz = dictamen_cfg.get("RECHAZADO", {})

        # Umbral base de APROBADO (default v1.0 = 80)
        umbral_aprobado_base = int(aprob.get("score_minimo", 80))

        # Ajuste por monto solicitado
        ajuste = self._monto_adjust(monto)
        umbral_aprobado = umbral_aprobado_base + ajuste

        # Floor de REVISION_MANUAL
        # Prioridad: floor absoluto si el JSON lo declara,
        # de lo contrario banda relativa de 20 (legacy v1.0).
        floor_absoluto = rechaz.get("score_maximo")
        if floor_absoluto is not None:
            umbral_revision = int(floor_absoluto) + 1
        else:
            umbral_revision = umbral_aprobado - 20

        if score >= umbral_aprobado:
            return "APROBADO"
        if score >= umbral_revision:
            return "REVISION_MANUAL"
        return "RECHAZADO"

    def _monto_adjust(self, monto: float) -> int:
        """Devuelve el ajuste al umbral según los tramos JSON."""
        thr = self._thresholds or {}
        tramos = (
            thr.get("monto_credito_modificador", {})
            .get("tramos", [])
        )
        for tramo in tramos:
            mn = float(tramo.get("monto_min", 0))
            mx = float(tramo.get("monto_max", 0))
            if mn <= monto <= mx:
                return int(tramo.get("ajuste_umbral", 0))
        return 0


# ════════════════════════════════════════════════════════════
# Demo CLI: A/B sobre los 5,248 observables
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    import time

    sys.path.insert(0, str(_PROJECT_ROOT))
    import pandas as pd

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-22s | %(message)s",
    )

    print("=" * 70)
    print("MIHAC v2.0 — Demo CalibratedEngine (env-var driven)")
    print("=" * 70)

    res_path = (
        _PROJECT_ROOT / "reports" / "backtesting_mx" / "results.csv"
    )
    if not res_path.exists():
        print(
            f"\nERROR: no existe {res_path}. Corre el Módulo B "
            "(validation/backtesting_mx.py) primero."
        )
        sys.exit(1)

    sample = pd.read_csv(res_path)

    # Compatibilidad: results.csv viene del backtester con _y de Module B
    base_cols = [
        "edad", "ingreso_mensual", "total_deuda_actual",
        "historial_crediticio", "antiguedad_laboral",
        "numero_dependientes", "tipo_vivienda",
        "proposito_credito", "monto_credito",
    ]

    # Ejecutar SIN env var (motor base)
    if _ENV_VAR in os.environ:
        del os.environ[_ENV_VAR]
    engine_base = CalibratedEngine()

    # Ejecutar CON env var (calibración MX)
    os.environ[_ENV_VAR] = "thresholds_mx.json"
    engine_mx = CalibratedEngine()

    print("\nUmbrales activos:")
    print(f"  base : {engine_base._thresholds_source or '(hardcoded v1.0)'}")
    print(f"  mx   : {engine_mx._thresholds_source}")

    print(f"\nA/B sobre {len(sample):,} filas observables ENIF...")
    t0 = time.perf_counter()
    dict_base: dict[str, int] = {}
    dict_mx: dict[str, int] = {}
    diffs = 0
    diff_examples: list[tuple] = []

    for _, row in sample.iterrows():
        datos = {k: row[k] for k in base_cols}
        for k in (
            "edad", "historial_crediticio",
            "antiguedad_laboral", "numero_dependientes",
        ):
            datos[k] = int(datos[k])
        for k in (
            "ingreso_mensual", "total_deuda_actual", "monto_credito",
        ):
            datos[k] = float(datos[k])
        for k in ("tipo_vivienda", "proposito_credito"):
            datos[k] = str(datos[k])

        r1 = engine_base.evaluate(datos)
        r2 = engine_mx.evaluate(datos)
        d1, d2 = r1["dictamen"], r2["dictamen"]
        dict_base[d1] = dict_base.get(d1, 0) + 1
        dict_mx[d2] = dict_mx.get(d2, 0) + 1
        if d1 != d2:
            diffs += 1
            if len(diff_examples) < 5:
                diff_examples.append(
                    (int(row["llavemod"]),
                     int(r1["score_final"]),
                     float(datos["monto_credito"]),
                     d1, d2)
                )

    elapsed = time.perf_counter() - t0
    print(f"\nDistribución de dictámenes ({len(sample):,} filas):")
    print(f"  {'Dictamen':18s}  {'base v1.0':>10s}  {'MX cal':>10s}")
    for d in ("APROBADO", "REVISION_MANUAL", "RECHAZADO"):
        print(
            f"  {d:18s}  "
            f"{dict_base.get(d, 0):>10,}  "
            f"{dict_mx.get(d, 0):>10,}"
        )
    print(f"\nFilas con dictamen distinto: {diffs:,} / {len(sample):,}")
    print(f"Tiempo: {elapsed:.2f} s ({elapsed/len(sample)*1000:.2f} ms/fila)")

    if diff_examples:
        print("\nEjemplos de fila reclasificada (base → MX):")
        for llave, score, monto, d1, d2 in diff_examples:
            print(
                f"  llavemod={llave} score={score} "
                f"monto=${monto:,.0f}  {d1} → {d2}"
            )
    print("=" * 70)
