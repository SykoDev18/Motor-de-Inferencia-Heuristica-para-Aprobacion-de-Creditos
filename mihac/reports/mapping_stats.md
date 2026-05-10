# Mapeo ENIF 2024 → MIHAC — Reporte de ejecución
**Generado:** 2026-05-10 11:36:55  
**Tiempo de ejecución:** 19.42 s  
**Filas procesadas:** 13,502  

## 1. Cobertura del mapeo

| Métrica | Valor |
|---|---:|
| Filas mapeadas | 13,502 |
| Ingreso imputado (mediana × niv) | 4,727 (35.0%) |
| Deuda imputada (DTI=0.30 sintético) | 13,502 (100.0%) |
| Excepciones del engine | 0 |

## 2. Distribución de dictámenes

| Dictamen | Filas | Porcentaje |
|---|---:|---:|
| APROBADO | 2,348 | 17.39% |
| REVISION_MANUAL | 1,664 | 12.32% |
| RECHAZADO | 9,490 | 70.29% |
| ERROR | 0 | 0.00% |

## 3. Distribución de DTI sintético

Por construcción, todas las filas deberían quedar en DTI=0.30 (MODERADO). Si aparecen otras clases, indica filas con ingreso muy bajo o errores numéricos.

| Clasificación | Filas |
|---|---:|
| MODERADO | 13,502 |

## 4. Estadísticas numéricas

| Variable | Min | Mediana | Media | Max |
|---|---:|---:|---:|---:|
| ingreso_mensual | $100 | $2,000 | $4,745 | $98,000 |
| score_final | 0 | 42 | 46.2 | 100 |

## 5. Distribuciones categóricas (mapeadas)

- **historial_crediticio** (0=Malo, 1=Neutro, 2=Bueno): `{0: 1184, 1: 8254, 2: 4064}`
- **tipo_vivienda**: `{'Familiar': 8188, 'Propia': 5314}`
- **proposito_credito**: `{'Consumo': 13193, 'Negocio': 309}`
- **antiguedad_laboral** (años): `{0: 4178, 1: 3035, 2: 2055, 3: 186, 4: 3818, 5: 230}`

## 6. Top reglas heurísticas activadas

| Regla | Activaciones | % de filas |
|---|---:|---:|
| R012 | 5,689 | 42.1% |
| R005 | 5,314 | 39.4% |
| R004 | 4,178 | 30.9% |
| R001 | 4,064 | 30.1% |
| R002 | 1,184 | 8.8% |
| R010 | 1,054 | 7.8% |
| R009 | 691 | 5.1% |
| R015 | 623 | 4.6% |
| R006 | 309 | 2.3% |
| R003 | 230 | 1.7% |

## 7. Comparación con tasas de mora CNBV (feb-2024)

| Indicador | Valor MIHAC sobre ENIF | Referencia CNBV |
|---|---:|---:|
| Tasa de rechazo del motor | 70.29% | n/a |
| Tasa de aprobación del motor | 17.39% | n/a |
| % historial Malo (derivado) | 8.77% | IMOR microcréditos = 3.5% |
| | | IMOR personales = 4.9% |

**Lectura:** la tasa de rechazo del motor refleja el perfil socioeconómico capturado por ENIF (bajos ingresos, alta proporción sin antigüedad formal). No es directamente comparable con IMOR — IMOR mide mora *ex post* sobre cartera colocada, mientras que MIHAC evalúa solicitudes hipotéticas con un monto fijo asignado por propósito.

## 8. Limitaciones de este mapeo

- ENIF no captura el monto absoluto de deuda; usamos DTI sintético = 0.30. Esto neutraliza R011, R013, R014 y el veto DTI por diseño.
- ENIF no captura monto del crédito solicitado; usamos medianas CNBV por propósito.
- ENIF no captura antigüedad laboral exacta; derivamos de p3_10 × p3_13.
- tipo_vivienda colapsa Rentada/Prestada en 'Familiar' (ENIF solo distingue propietario sí/no vía p13_2_1).
- proposito_credito es una traducción gruesa del tipo de crédito tenido (p6_2_x); no refleja la intención de uso de un crédito hipotético nuevo.
