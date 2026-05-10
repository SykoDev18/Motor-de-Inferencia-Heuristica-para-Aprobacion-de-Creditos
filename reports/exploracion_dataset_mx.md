# Módulo A — Reporte de exploración de datasets mexicanos

**Fecha:** 2026-05-10
**Autor:** Sesión de exploración (sin implementación todavía)
**Ámbito:** Caracterizar los datasets en `mihac/DataSet/` y producir la
tabla de mapeo `ENIF 2024 ↔ MIHAC v1.0` antes de escribir el mapper.

---

## 1. Inventario de archivos en `mihac/DataSet/`

| Carpeta / archivo | Tipo | Uso para MIHAC |
|---|---|---|
| `ENIF 2024/conjunto_de_datos_enif_2024_csv/` | Microdatos INEGI (CSV + diccionarios + catálogos) | **Fuente principal del Módulo A** |
| `Base_de_Datos_de_Inclusion_Financiera_202506.xlsx` | Agregados CNBV por municipio/estado/banca | **Módulo G** (calibración), no A |
| `enif_2024_tab_18_a_70_anios_*_xlsx/` (5 carpetas) | Tabulados precalculados ENIF (ahorro, capacidades, comportamiento, crédito, pagos) | Contexto / paper, no mapeo |
| `Rúbrica de Evaluación proyecto heurístico..pdf` | Rúbrica académica | Fuera de alcance |

---

## 2. Estructura de ENIF 2024 (microdatos INEGI)

ENIF 2024 está dividida en **4 tablas** unidas por llaves jerárquicas
`llaveviv → llavehog → {llavesde, llavemod}`:

| Tabla | Filas | Cols | Tamaño | Granularidad | Contenido |
|---|---:|---:|---:|---|---|
| `tvivienda` | 13,303 | 19 | 0.68 MB | 1 fila / vivienda | Cuartos, auto, internet (NO tipo de vivienda) |
| `thogar` | 13,508 | 9 | 0.52 MB | 1 fila / hogar | Solo `p2_8` = # personas con trabajo remunerado |
| `tsdem` | 44,374 | 17 | 3.04 MB | 1 fila / persona | edad, sexo, parentesco, escolaridad |
| **`tmodulo`** | **13,502** | **398** | **8.68 MB** | 1 fila / persona seleccionada (mayor de edad por hogar) | **Todo el contenido financiero** |

### Llaves de unión

```
tvivienda.llaveviv ─┬─ thogar.llaveviv
                    └─ tsdem.llaveviv     (paren=1 → jefe del hogar)
                       │
                       └─ llavehog ─── tmodulo.llavehog
```

**Unidad de análisis recomendada para MIHAC:** una fila por persona del
módulo (`tmodulo`, 13,502 registros), enriquecida con datos de su hogar
(`thogar`), su vivienda (`tvivienda`) y los miembros de su hogar
(`tsdem` agregado por `llavehog`).

### Nulls y dtypes (tablas pequeñas)

- **tvivienda**: 19 cols, mayoría int64. Algunas float64 (NaN cuando la
  pregunta no aplica): `p0_4_1a` (# autos solo si tiene), `p0_4_2a` (Internet fijo solo si tiene), `p1_3` (# hogares solo si >1).
- **thogar**: 9 cols, todas int64, **sin nulls**. Pero solo aporta `p2_8`.
- **tsdem**: 17 cols, todas int64 excepto `niv` y `gra` que son float64
  (NaN para menores que aún no escolarizan). `niv` y `gra` tienen
  30,866 nulls (~70%) — esperado.
- **tmodulo**: 398 cols. La mayoría int64; las preguntas con filtro
  (solo aplican si tiene producto) son float64 con NaN cuando no aplica.

---

## 3. CNBV — Base de Datos de Inclusión Financiera 202506

| Hoja | Filas × Cols | Contenido |
|---|---:|---|
| `BD Infraestructura Mun` | 2,487 × 48 | Sucursales/cajeros por municipio |
| `BD Crédito Mun` | 2,487 × 50 | Colocación de crédito por municipio |
| `BD Crédito Edo` | 45 × 49 | Crédito por estado |
| `BD por sexo Banca Mun` | 2,487 × 108 | Crédito desagregado por sexo |
| `BD Datos históricos` | 70 × 65 | Series temporales nacionales |
| (otras 13 hojas) | — | Captación, ficha técnica, EACP |

**Conclusión:** Es agregada (no a nivel persona). **No participa en el
mapeo del Módulo A.** Reservar para Módulo G — calibración de umbrales
con IMOR real por segmento.

---

## 4. Tabla de mapeo MIHAC v1.0 ↔ ENIF 2024

Las **9 variables de entrada** de MIHAC, su correspondencia en ENIF y la
acción requerida:

| # | Variable MIHAC | Tipo | ENIF — columna(s) | Tabla | Acción | Calidad |
|---|---|---|---|---|---|---|
| 1 | `edad` | int 18–99 | `edad` (años cumplidos) | tsdem | **Mapeo directo** desde tsdem del seleccionado | ✅ Perfecta — 0 nulls |
| 2 | `ingreso_mensual` | float MXN > 0 | `p3_11a` ("¿Cuánto gana o recibe usted por trabajar?") + `p3_12` (frecuencia: 1=¿mensual? 2=¿quincenal/semanal?) | tmodulo | **Normalizar a mensual** usando `p3_12` + limpiar sentinels (`99888`/`99999` = NS/NR) | ⚠️ 30.6% nulls (no trabaja / no responde); rango $500–$99,000+ |
| 3 | `total_deuda_actual` | float ≥ 0 | **No existe monto exacto.** Proxy: `p6_7` ("¿considera su carga de deuda...?" 1=alta…4=ninguna) + tenencia agregada de `p6_2_1..p6_2_9` | tmodulo | **Derivar** índice ordinal de deuda y/o calcular DTI relativo a partir de `p6_7` | ❌ ENIF no captura monto. Esto rompe el cálculo exacto de DTI; hay que inventar un proxy o dejarla nula y activar reglas de compensación |
| 4 | `historial_crediticio` | int {0,1,2} | `p6_3_1..p6_3_9` (atrasos por tipo de crédito) + `p4_4_7` (atraso cuando no pudo cubrir gastos) | tmodulo | **Derivar:** • cualquier `p6_3_x==1` → 0=Malo; • tiene crédito y todos los `p6_3_x==2` → 2=Bueno; • sin crédito en últimos 12m → 1=Neutro | ✅ Excelente fit con la lógica MIHAC (especialmente la regla R011 que premia historial Neutro) |
| 5 | `antiguedad_laboral` | int años ≥ 0 | **No existe.** Proxies débiles: `p3_10` (situación: empleado/empleador/cuenta propia/etc.), `p3_13` (acceso a servicios médicos = formalidad) | tmodulo | **Imputación** o constante neutra. Considerar reportarla como NaN y dejar que las reglas R003/R004 no se activen | ❌ Pérdida importante: R003 (+15 si ≥5 años), R004 (-10 si <1), R011/R013/R015 dependen de antigüedad |
| 6 | `numero_dependientes` | int ≥ 0 | Contar miembros del hogar con `paren ∈ {3, 4}` (hijo, otro pariente) en tsdem agrupando por `llavehog` | tsdem (agregado) | **Derivar** vía `groupby(llavehog).size()` filtrando parentesco | ✅ Limpio. Promedio 3.28 personas/hogar (mediana 3) — alineado con censo MX |
| 7 | `tipo_vivienda` | str {Propia, Rentada, Prestada, Otro} | `p13_2_1` (¿usted es propietario de alguna vivienda?) — solo binario | tmodulo | **Mapear:** `p13_2_1==1` → "Propia", `p13_2_1==2` → "Otro" (sin posibilidad de distinguir Rentada vs Prestada) | ⚠️ Pérdida de granularidad. R005 (+10 si Propia) sí se puede activar; las demás opciones colapsan a "Otro" |
| 8 | `proposito_credito` | str {Negocio, Educacion, Personal, Vacaciones, Emergencia} | **No hay pregunta directa.** Inferir desde el tipo de crédito tenido `p6_2_1..p6_2_9` | tmodulo | **Heurística de mapeo:** • crédito automotriz/vivienda/personal/nómina → "Personal"; • grupal-comunal (p6_2_7, tipo Compartamos) → "Negocio"; • departamental → "Personal" | ⚠️ Aproximación grosera. Si solicita por primera vez, no hay propósito histórico. Para backtesting, asumir que el último crédito tenido refleja el propósito |
| 9 | `monto_credito` | float [500, 50000] | **No existe.** ENIF no captura montos contratados | n/a | **Sintetizar** valor representativo o usar agregados CNBV por tipo de producto y entidad, o saltarse la regla del veto-monto | ❌ Variable de control crítica para MIHAC (eleva el umbral según tamaño). Sin ella, todas las solicitudes serían tratadas como "micro" |

### Resumen de cobertura

- ✅ **Mapeo directo (3/9):** edad, historial_crediticio (derivable limpio), tipo_vivienda (limpio si aceptamos colapsar a binario)
- ⚠️ **Derivación con pérdida (3/9):** ingreso_mensual (limpiar sentinels), numero_dependientes (agregar tsdem), proposito_credito (heurística cruda)
- ❌ **No disponibles en ENIF (3/9):** total_deuda_actual (solo nivel subjetivo), antiguedad_laboral (no existe), monto_credito (no existe)

**Cobertura efectiva estimada para `InferenceEngine.evaluate()`:** ~67%
de las variables se pueden poblar con calidad razonable. Las 3 faltantes
forzarán activación de **reglas de compensación** o requerirán
imputación con valores por defecto declarados.

---

## 5. Variable objetivo (para Módulo C — modelo ML)

ENIF 2024 sí permite construir una variable binaria de
buen-pagador / mal-pagador a partir de los **9 indicadores de atraso**:

```text
target_buen_pagador = 1   si tiene ≥1 crédito en p6_2_x  AND  todos los p6_3_x ∈ {2 (No), NaN}
                    = 0   si tiene ≥1 crédito  AND  cualquier p6_3_x == 1 (Sí, atraso)
                    = NaN si no tiene ningún crédito (no hay outcome)
```

Población útil para entrenamiento ML estimada (a verificar al
implementar Módulo A): los registros con al menos un `p6_2_x == 1`. En
la muestra observada `p6_3_1` tiene 23% no-nulls (~3,110 registros con
historial de tarjeta departamental), `p6_3_2` ~16%, etc. Con la unión
de los 9 tipos, la población elegible probablemente supere 5,000
registros — suficiente para ML supervisado.

---

## 6. Riesgos y decisiones a tomar antes de implementar el mapper

| # | Riesgo | Decisión requerida |
|---|---|---|
| R1 | `ingreso_mensual` tiene sentinels `99888` (probable NS) y posibles `99999` (NR). Si se cuelan, MIHAC los toma como ingreso real altísimo y aprueba todo. | ¿Imputar con mediana del estrato?, ¿descartar la fila?, ¿asignar NaN y bloquear evaluación? |
| R2 | `p3_12` (frecuencia) decide la normalización a mensual. Hay que confirmar el catálogo: si vale 1=mensual o 1=semanal el ingreso se distorsiona 4×. | Leer `catalogos/p3_12.csv` antes de implementar |
| R3 | `total_deuda_actual` no existe. ¿Calculamos un DTI sintético desde `p6_7` (1=alta deuda → DTI=0.5; 4=sin deuda → DTI=0)? ¿O dejamos `total_deuda_actual=0` y perdemos R014/R011? | Proponer escala: `p6_7=1→DTI=0.50, =2→0.30, =3→0.15, =4→0.0` (a calibrar con CNBV en Módulo G) |
| R4 | `antiguedad_laboral` no existe. | Decisión binaria: (a) imputar con la mediana nacional (~5 años por ENOE), (b) marcar como NaN y desactivar reglas dependientes, (c) usar `p3_13` como proxy (formalidad ⇒ antigüedad ≥3 años) |
| R5 | `proposito_credito` desde `p6_2_x` es una traducción con pérdida. | Validar el mapeo con el experto de tesis antes de codificarlo |
| R6 | `monto_credito` no existe en ENIF. | Sintetizar (ej. mediana CNBV por tipo de crédito) o reportar la limitación en el paper |
| R7 | Sólo 1 persona por hogar fue seleccionada para el módulo. La unidad de análisis MIHAC es una persona, no un hogar — coincide perfecto. | Confirmar que el join usa `llavemod`/`llavehog` 1:1 |

---

## 7. Próximos pasos (al implementar el Módulo A)

1. Leer **catálogos** clave: `p3_12`, `p6_2_x`, `p6_7`, `p13_2_1`,
   `p3_10` para confirmar la semántica de cada código.
2. Resolver R1–R7 con el dueño del proyecto (decisiones de imputación
   y escalas).
3. Implementar `data/mapper_enif.py` con función
   `map_enif_row_to_mihac(seleccion, hogar, vivienda, miembros) → dict`.
4. Probar `InferenceEngine().evaluate(...)` con 100 filas mapeadas y
   medir el % de filas que pasan validación.
5. Generar `reports/enif_mapped.csv` y `reports/mapping_stats.md`
   (cobertura, distribuciones, casos descartados).

---

## 8. Comandos reproducibles

```powershell
# 1) Verificar pandas
.venv\Scripts\python.exe -c "import pandas as pd; print(pd.__version__)"

# 2) Leer microdatos ENIF
$base = "mihac/DataSet/ENIF 2024/conjunto_de_datos_enif_2024_csv"
.venv\Scripts\python.exe -c "
import pandas as pd
mod = pd.read_csv(r'$base/conjunto_de_datos_tmodulo_enif_2024/conjunto_de_datos/conjunto_de_datos_tmodulo_enif2024.csv', low_memory=False)
print(mod.shape, mod.columns[:10].tolist())
"

# 3) Diccionario tmodulo
.venv\Scripts\python.exe -c "
import pandas as pd
d = pd.read_csv(r'$base/conjunto_de_datos_tmodulo_enif_2024/diccionario_de_datos/diccionario_datos_tmodulo_enif2024.csv', encoding='utf-8', on_bad_lines='skip')
print(d.shape); print(d.head(20))
"
```
