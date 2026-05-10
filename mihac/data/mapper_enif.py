# ============================================================
# MIHAC v2.0 — Mapper del dataset ENIF 2024 (INEGI)
# data/mapper_enif.py
# ============================================================
# Convierte los microdatos de la Encuesta Nacional de Inclusión
# Financiera 2024 (México, INEGI) al formato de 9 variables de
# entrada que consume InferenceEngine v1.0.
#
# Fuente: INEGI. Encuesta Nacional de Inclusión Financiera 2024.
#         https://www.inegi.org.mx/programas/enif/2024/
#
# Tablas requeridas (CSV bajo conjunto_de_datos_enif_2024_csv/):
#   - tmodulo  (398 cols, 1 fila por persona seleccionada)
#   - tsdem    (17 cols, 1 fila por residente del hogar)
#
# DECISIONES DOCUMENTADAS (acordadas con el dueño del proyecto):
#
# 1. INGRESO  (sentinels p3_11a):
#    - 00000 = no recibe ingresos          → imputar
#    - 99888 = no responde                  → imputar
#    - resto = monto mensual válido
#    Imputación: mediana agrupada por escolaridad (`niv` en
#    tmodulo). Si la mediana del grupo es NaN, se usa la mediana
#    global; último fallback: 5,000 MXN. Cada fila imputada
#    queda marcada con ingreso_imputado=True.
#
# 2. DEUDA TOTAL ABSOLUTA (no existe en ENIF):
#    Se imputa `total_deuda_actual = 0.30 × ingreso_mensual`
#    (DTI sintético = 0.30 → clasificación MODERADO). Esto
#    suprime el veto DTI y las reglas que dependen de deuda:
#       - R014 (DTI > 0.40):       0.30 < 0.40 → no fira
#       - R011 (DTI < 0.25):       0.30 > 0.25 → no fira
#       - R013 (deuda == 0):       no fira
#    Cada fila se marca con deuda_imputada_neutra=True.
#
# 3. ANTIGÜEDAD LABORAL (no existe en ENIF):
#    Se deriva combinando p3_10 (situación laboral) y p3_13
#    (servicios médicos del trabajo, proxy de formalidad):
#       p3_10=1 ∧ p3_13∈{1..6}  → 4 años (empleado formal)
#       p3_10=1 ∧ p3_13=7       → 2 años (empleado informal)
#       p3_10=4                 → 5 años (patrón/empleador)
#       p3_10=5 ∧ p3_13∈{1..6}  → 3 años (cuenta propia formal)
#       p3_10=5 ∧ p3_13=7       → 1 año  (cuenta propia informal)
#       p3_10=2                 → 1 año  (jornalero)
#       p3_10=3                 → 1 año  (ayudante con pago)
#       p3_10=6                 → 0 años (sin pago)
#       p3_10 NaN  /  p3_13=9   → 0 años (sin empleo / NS)
#    Se aplica además el cap de coherencia: antig ≤ edad − 15.
#
# 4. MONTO DEL CRÉDITO (no existe en ENIF):
#    Asignación por propósito derivado (medianas CNBV 2024):
#       Negocio    → 12,000
#       Educacion  →  8,000
#       Emergencia →  5,000
#       Consumo    → 10,000
#       Vacaciones →  8,000
#    Posteriormente acotado a [500, min(50000, 18 × ingreso)]
#    para satisfacer las validaciones C009 y D003.
#
# 5. PROPÓSITO DEL CRÉDITO (no existe en ENIF de forma directa):
#    Se infiere del tipo de crédito tenido (p6_2_1..p6_2_9).
#    Crédito grupal/comunal (Compartamos) → "Negocio".
#    Cualquier otro tipo → "Consumo". Sin créditos vigentes
#    también se asigna "Consumo" como hipótesis por defecto.
#
# 6. TIPO DE VIVIENDA:
#    p13_2_1 (¿es propietario de alguna vivienda?) es binaria.
#       1 → "Propia"     |     2 / NaN → "Familiar"
#    ENIF no distingue Rentada vs Familiar; colapsamos al valor
#    aceptado por el validator que mejor representa "no propia"
#    en el contexto mexicano.
#
# 7. DEPENDIENTES:
#    Se cuentan los miembros del hogar (tsdem) con
#    paren ∈ {3 hijo, 4 otro pariente}, agregados por llavehog
#    y truncados a [0, 10] para satisfacer C006.
# ============================================================

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Rutas de los CSV de ENIF 2024 (relativas al proyecto) ────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENIF_BASE = (
    _PROJECT_ROOT
    / "DataSet"
    / "ENIF 2024"
    / "conjunto_de_datos_enif_2024_csv"
)
_TMODULO_CSV = (
    _ENIF_BASE
    / "conjunto_de_datos_tmodulo_enif_2024"
    / "conjunto_de_datos"
    / "conjunto_de_datos_tmodulo_enif2024.csv"
)
_TSDEM_CSV = (
    _ENIF_BASE
    / "conjunto_de_datos_tsdem_enif_2024"
    / "conjunto_de_datos"
    / "conjunto_de_datos_tsdem_enif2024.csv"
)

# ── Constantes de mapeo ──────────────────────────────────────

# Sentinels documentados en catalogos/p3_11a.csv
_INGRESO_SENTINEL_NS = 99888  # "No responde"
_INGRESO_SENTINEL_NULO = 0    # "No recibe ingresos"
_INGRESO_FALLBACK = 5000.0    # Último fallback si todo falla

# Piso mínimo razonable de ingreso laboral en MXN/mes. Por debajo
# de este valor lo tratamos como error de captura (típico patrón
# en encuestas: el respondente dice "15 mil" y se captura como
# "15"). Adicionalmente, valores < 28 generan un conflicto interno
# entre C009 (monto ≥ 500) y D003 (monto ≤ 18 × ingreso) en el
# validator, lo que produciría rechazos por motivo distinto al
# crediticio. Imputamos con mediana × niv en ese caso.
_INGRESO_PISO_MINIMO = 100.0

# Factor de DTI sintético (deuda imputada como ratio del ingreso)
_DTI_NEUTRO = 0.30

# Montos por propósito (medianas CNBV 2024 — segmentos de microcrédito)
_MONTO_POR_PROPOSITO: dict[str, float] = {
    "Negocio":    12000.0,
    "Educacion":   8000.0,
    "Emergencia":  5000.0,
    "Consumo":    10000.0,
    "Vacaciones":  8000.0,
}

# Identificadores de las 9 columnas binarias de tenencia de crédito
_COLS_TENENCIA = [f"p6_2_{i}" for i in range(1, 10)]

# Columnas pareadas de "¿se atrasó?" por tipo de crédito
_COLS_ATRASO = [f"p6_3_{i}" for i in range(1, 10)]


# ── Derivaciones individuales (puras, testeables) ────────────

def derive_antiguedad(p3_10: float, p3_13: float) -> int:
    """Deriva años de antigüedad laboral a partir de p3_10 y p3_13.

    Args:
        p3_10: Situación laboral (1..6) o NaN.
        p3_13: Acceso a servicios médicos del trabajo
            (1..7, 9) o NaN.

    Returns:
        Años (int) en el rango [0, 5].

    Ejemplos::

        derive_antiguedad(1, 1) == 4   # empleado formal
        derive_antiguedad(1, 7) == 2   # empleado informal
        derive_antiguedad(4, 9) == 5   # patrón/empleador
    """
    if pd.isna(p3_10):
        return 0

    p10 = int(p3_10)
    p13 = int(p3_13) if pd.notna(p3_13) else 9
    formal = 1 <= p13 <= 6
    informal = p13 == 7

    if p10 == 1 and formal:
        return 4
    if p10 == 1 and informal:
        return 2
    if p10 == 4:
        return 5
    if p10 == 5 and formal:
        return 3
    if p10 == 5 and informal:
        return 1
    if p10 == 2:
        return 1
    if p10 == 3:
        return 1
    if p10 == 6:
        return 0
    return 0


def derive_historial(row: pd.Series) -> int:
    """Deriva historial_crediticio (0/1/2) desde p6_2_x y p6_3_x.

    Lógica:
        - Sin créditos vigentes en últimos 12m → 1 (Neutro)
        - Con créditos y algún atraso (p6_3_x == 1) → 0 (Malo)
        - Con créditos y sin atrasos → 2 (Bueno)

    Args:
        row: Fila de tmodulo con columnas p6_2_1..p6_2_9 y
            p6_3_1..p6_3_9.

    Returns:
        0=Malo, 1=Neutro, 2=Bueno.
    """
    tipos_tenidos = sum(
        1 for col in _COLS_TENENCIA if row.get(col) == 1
    )
    if tipos_tenidos == 0:
        return 1  # Neutro: sin información de pago

    for col in _COLS_ATRASO:
        if row.get(col) == 1:  # 1 = sí hubo atraso
            return 0  # Malo

    return 2  # Bueno: tiene crédito y todos al corriente


def derive_proposito(row: pd.Series) -> str:
    """Deriva proposito_credito desde el tipo de crédito tenido.

    Prioridad:
        1. Crédito grupal/comunal (p6_2_7) → 'Negocio' (típico
           microcrédito productivo, ej. Compartamos).
        2. Cualquier otro tipo de crédito vigente → 'Consumo'.
        3. Sin créditos vigentes → 'Consumo' como hipótesis
           por defecto del producto de microcrédito a evaluar.

    Args:
        row: Fila de tmodulo con columnas p6_2_1..p6_2_9.

    Returns:
        Uno de los 5 propósitos válidos del validator v1.0.
    """
    if row.get("p6_2_7") == 1:
        return "Negocio"
    return "Consumo"


def derive_tipo_vivienda(p13_2_1: float) -> str:
    """Deriva tipo_vivienda desde p13_2_1 (propietario sí/no).

    Args:
        p13_2_1: 1=Sí propietario, 2=No, NaN=no aplica.

    Returns:
        'Propia' | 'Familiar' (no se distingue Rentada en ENIF).
    """
    if pd.isna(p13_2_1):
        return "Familiar"
    return "Propia" if int(p13_2_1) == 1 else "Familiar"


# ── Saneamiento de ingreso e imputación por escolaridad ──────

def sanitize_ingreso(
    ingreso_raw: pd.Series, niv: pd.Series
) -> tuple[pd.Series, pd.Series]:
    """Limpia sentinels e imputa ingresos faltantes.

    Args:
        ingreso_raw: Serie cruda de p3_11a.
        niv: Serie de escolaridad (`niv`) usada para agrupar la
            mediana imputadora.

    Returns:
        (ingreso_final, mascara_imputado)
        - ingreso_final: float > 0, garantizado.
        - mascara_imputado: bool, True donde se imputó.
    """
    # Reemplazar sentinels, valores no positivos y valores
    # absurdamente bajos (ver _INGRESO_PISO_MINIMO) por NaN
    ingreso = ingreso_raw.where(
        (ingreso_raw >= _INGRESO_PISO_MINIMO)
        & (ingreso_raw < _INGRESO_SENTINEL_NS)
    )

    mascara_imputado = ingreso.isna()

    # Mediana por nivel de escolaridad (excluyendo nulos)
    niv_clean = niv.fillna(99)
    median_by_niv = ingreso.groupby(niv_clean).median()
    overall_median = ingreso.median()

    # Plan de relleno: niv-median → global-median → fallback
    fill_step1 = niv_clean.map(median_by_niv)
    fill_step2 = fill_step1.fillna(overall_median)
    fill_final = fill_step2.fillna(_INGRESO_FALLBACK)

    ingreso_final = ingreso.fillna(fill_final)

    # Garantía dura: nunca permitir 0 o negativos
    ingreso_final = ingreso_final.where(
        ingreso_final > 0, _INGRESO_FALLBACK
    )

    return ingreso_final.round(2), mascara_imputado


# ── Conteo de dependientes por hogar ─────────────────────────

def count_dependientes(tsdem: pd.DataFrame) -> pd.Series:
    """Cuenta dependientes por hogar (paren ∈ {hijo, otro pariente}).

    Args:
        tsdem: Tabla sociodemográfica completa.

    Returns:
        Serie indexada por llavehog con el conteo de miembros
        cuyo parentesco es 3 (hijo/a) o 4 (otro pariente).
        Truncado a 10 para satisfacer C006 del validator.
    """
    deps = (
        tsdem[tsdem["paren"].isin([3, 4])]
        .groupby("llavehog")
        .size()
    )
    return deps.clip(upper=10)


# ── Función principal ────────────────────────────────────────

def map_enif_to_mihac(
    tmodulo: pd.DataFrame, tsdem: pd.DataFrame
) -> pd.DataFrame:
    """Mapea ENIF 2024 al formato MIHAC v1.0.

    Cada fila de tmodulo (persona seleccionada) se convierte en
    una fila de salida con las 9 variables de entrada que
    consume InferenceEngine.evaluate(), más metadata de
    auditoría (flags de imputación, llaves originales).

    Args:
        tmodulo: DataFrame con la tabla del módulo financiero.
        tsdem: DataFrame con la tabla sociodemográfica
            completa (para derivar dependientes por hogar).

    Returns:
        DataFrame con columnas:
            edad, ingreso_mensual, total_deuda_actual,
            historial_crediticio, antiguedad_laboral,
            numero_dependientes, tipo_vivienda,
            proposito_credito, monto_credito,
            ingreso_imputado, deuda_imputada_neutra,
            llavemod, llavehog (auditoría).
    """
    n = len(tmodulo)
    logger.info("Mapeando %d filas de tmodulo a formato MIHAC", n)

    # ── 1. Edad ─────────────────────────────────────────────
    edad = (
        tmodulo["edad_v"]
        .astype(int)
        .clip(lower=18, upper=99)
    )

    # ── 2. Ingreso (con imputación por escolaridad) ─────────
    ingreso_final, mascara_imputado = sanitize_ingreso(
        tmodulo["p3_11a"], tmodulo["niv"]
    )

    # ── 3. Deuda total (sintética, DTI=0.30) ────────────────
    deuda = (ingreso_final * _DTI_NEUTRO).round(2)

    # ── 4. Historial crediticio ─────────────────────────────
    historial = tmodulo.apply(derive_historial, axis=1).astype(int)

    # ── 5. Antigüedad laboral ───────────────────────────────
    antig_raw = pd.Series(
        [
            derive_antiguedad(p10, p13)
            for p10, p13 in zip(tmodulo["p3_10"], tmodulo["p3_13"])
        ],
        index=tmodulo.index,
    )
    # Cap por coherencia D001 (antig ≤ edad − 15)
    antig = np.minimum(antig_raw, edad - 15).clip(lower=0).astype(int)

    # ── 6. Número de dependientes (desde tsdem) ─────────────
    deps_por_hogar = count_dependientes(tsdem)
    deps = (
        tmodulo["llavehog"]
        .map(deps_por_hogar)
        .fillna(0)
        .astype(int)
        .clip(lower=0, upper=10)
    )

    # ── 7. Tipo de vivienda ─────────────────────────────────
    vivienda = tmodulo["p13_2_1"].apply(derive_tipo_vivienda)

    # ── 8. Propósito del crédito ────────────────────────────
    proposito = tmodulo.apply(derive_proposito, axis=1)

    # ── 9. Monto del crédito (cap por D003 y C009) ──────────
    monto_base = proposito.map(_MONTO_POR_PROPOSITO)
    cap_d003 = ingreso_final * 18.0  # límite de coherencia
    monto = np.minimum(monto_base, cap_d003)
    monto = np.minimum(monto, 50000.0)
    monto = np.maximum(monto, 500.0)
    monto = monto.round(2)

    # ── Construir DataFrame de salida ───────────────────────
    out = pd.DataFrame(
        {
            # 9 variables MIHAC (orden del validator)
            "edad": edad.values,
            "ingreso_mensual": ingreso_final.values,
            "total_deuda_actual": deuda.values,
            "historial_crediticio": historial.values,
            "antiguedad_laboral": antig.values,
            "numero_dependientes": deps.values,
            "tipo_vivienda": vivienda.values,
            "proposito_credito": proposito.values,
            "monto_credito": monto.values,
            # Metadata de auditoría
            "ingreso_imputado": mascara_imputado.values,
            "deuda_imputada_neutra": True,
            "llavemod": tmodulo["llavemod"].values,
            "llavehog": tmodulo["llavehog"].values,
        }
    )

    return out


def to_mihac_dict(row: pd.Series) -> dict:
    """Convierte una fila mapeada al dict que espera evaluate().

    Filtra los campos de auditoría (ingreso_imputado, llaves) y
    asegura los tipos exactos: int para enteros, float para
    numéricos, str para textos.
    """
    return {
        "edad": int(row["edad"]),
        "ingreso_mensual": float(row["ingreso_mensual"]),
        "total_deuda_actual": float(row["total_deuda_actual"]),
        "historial_crediticio": int(row["historial_crediticio"]),
        "antiguedad_laboral": int(row["antiguedad_laboral"]),
        "numero_dependientes": int(row["numero_dependientes"]),
        "tipo_vivienda": str(row["tipo_vivienda"]),
        "proposito_credito": str(row["proposito_credito"]),
        "monto_credito": float(row["monto_credito"]),
    }


# ── Carga de los CSV de ENIF (helper de conveniencia) ────────

def load_enif_tables(
    base_dir: Path | str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carga las tablas tmodulo y tsdem necesarias para el mapeo.

    Args:
        base_dir: Carpeta raíz `conjunto_de_datos_enif_2024_csv/`.
            Si es None, usa la ruta por defecto del proyecto.

    Returns:
        (tmodulo, tsdem) como DataFrames.
    """
    if base_dir is None:
        tmod_path = _TMODULO_CSV
        tsd_path = _TSDEM_CSV
    else:
        base = Path(base_dir)
        tmod_path = (
            base
            / "conjunto_de_datos_tmodulo_enif_2024"
            / "conjunto_de_datos"
            / "conjunto_de_datos_tmodulo_enif2024.csv"
        )
        tsd_path = (
            base
            / "conjunto_de_datos_tsdem_enif_2024"
            / "conjunto_de_datos"
            / "conjunto_de_datos_tsdem_enif2024.csv"
        )

    logger.info("Leyendo tmodulo: %s", tmod_path)
    tmod = pd.read_csv(tmod_path, low_memory=False)
    logger.info("Leyendo tsdem: %s", tsd_path)
    tsd = pd.read_csv(tsd_path, low_memory=False)
    return tmod, tsd


# ════════════════════════════════════════════════════════════
# CLI: muestra de 100 filas + verificación con InferenceEngine
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    # Asegurar import del motor (mismo patrón que core/engine.py)
    sys.path.insert(0, str(_PROJECT_ROOT))
    from core.engine import InferenceEngine  # noqa: E402

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s | %(name)-15s | %(message)s",
    )

    print("=" * 70)
    print("MIHAC v2.0 — Mapper ENIF 2024 — Prueba con 100 filas")
    print("=" * 70)

    # Cargar y mapear
    tmod, tsd = load_enif_tables()
    print(f"\nTablas cargadas — tmodulo: {tmod.shape}, tsdem: {tsd.shape}")

    # Muestra estratificada: primeras 100 filas (determinista)
    sample = tmod.head(100).copy()
    mapped = map_enif_to_mihac(sample, tsd)

    # ── Mostrar tabla resumen ──
    print("\n" + "─" * 70)
    print("OUTPUT: 9 variables MIHAC + flags de auditoría (head 15)")
    print("─" * 70)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    print(mapped.head(15).to_string(index=False))

    # ── Estadísticas del mapeo ──
    print("\n" + "─" * 70)
    print("ESTADÍSTICAS DEL MAPEO (n=100)")
    print("─" * 70)
    print(f"  ingreso_imputado:        {mapped['ingreso_imputado'].sum()} filas")
    print(f"  ingreso (min/med/max):   "
          f"${mapped['ingreso_mensual'].min():,.0f} / "
          f"${mapped['ingreso_mensual'].median():,.0f} / "
          f"${mapped['ingreso_mensual'].max():,.0f}")
    print(f"  edad (min/med/max):      "
          f"{mapped['edad'].min()} / {int(mapped['edad'].median())} / "
          f"{mapped['edad'].max()}")
    print(f"  antiguedad (distrib):    "
          f"{mapped['antiguedad_laboral'].value_counts().sort_index().to_dict()}")
    print(f"  historial (distrib):     "
          f"{mapped['historial_crediticio'].value_counts().sort_index().to_dict()}")
    print(f"  tipo_vivienda (distrib): "
          f"{mapped['tipo_vivienda'].value_counts().to_dict()}")
    print(f"  proposito (distrib):     "
          f"{mapped['proposito_credito'].value_counts().to_dict()}")
    print(f"  dependientes (distrib):  "
          f"{mapped['numero_dependientes'].value_counts().sort_index().to_dict()}")
    print(f"  monto (min/med/max):     "
          f"${mapped['monto_credito'].min():,.0f} / "
          f"${mapped['monto_credito'].median():,.0f} / "
          f"${mapped['monto_credito'].max():,.0f}")

    # ── Verificar que InferenceEngine no lanza excepciones ──
    print("\n" + "─" * 70)
    print("VERIFICACIÓN: InferenceEngine().evaluate() sobre las 100 filas")
    print("─" * 70)

    engine = InferenceEngine()
    excepciones = 0
    con_errores_validacion = 0
    dictamenes: dict[str, int] = {}

    for i, fila in mapped.iterrows():
        datos = to_mihac_dict(fila)
        try:
            res = engine.evaluate(datos)
        except Exception as e:
            excepciones += 1
            print(f"  ⚠ Fila {i}: EXCEPCIÓN no capturada → {e}")
            continue

        if res.get("errores_validacion"):
            con_errores_validacion += 1
            if con_errores_validacion <= 3:
                print(
                    f"  ⚠ Fila {i}: errores_validacion = "
                    f"{res['errores_validacion']}"
                )
                print(f"     datos = {datos}")

        d = res.get("dictamen", "N/A")
        dictamenes[d] = dictamenes.get(d, 0) + 1

    print(f"\n  Excepciones lanzadas:        {excepciones} / 100")
    print(f"  Filas con errores_validacion: {con_errores_validacion} / 100")
    print(f"  Distribución de dictámenes:  {dictamenes}")

    if excepciones == 0:
        print("\n  ✓ PASS — InferenceEngine no lanzó ninguna excepción")
    else:
        print("\n  ✗ FAIL — hubo excepciones; revisar arriba")

    print("\n" + "=" * 70)
