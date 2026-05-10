# Backtesting MIHAC v1.0 con ENIF 2024 (México) — Reporte
**Generado:** 2026-05-10 11:45:51  
**Universo ENIF:** 13,502 personas seleccionadas  
**Población observable** (con ≥1 crédito vigente): 5,248 (38.87%)  
**Tiempo de ejecución:** 4.51 s  

## 1. Construcción del target

El target binario se construye desde la mora autodeclarada en ENIF (p6_3_x):

- `y_real = 1` (buen pagador): tiene ≥1 crédito en p6_2_x y ningún p6_3_x == 1.
- `y_real = 0` (mal pagador): tiene ≥1 crédito y al menos un p6_3_x == 1.
- Personas sin crédito vigente quedan fuera del backtest (no hay outcome observable).

**Distribución del target** (n=5,248):

- Buenos pagadores (y=1): 4,064 (77.4%)
- Malos pagadores  (y=0): 1,184 (22.6%)

Tasa de mora autodeclarada: 22.56% — comparar con IMOR CNBV (microcréditos) = 3.5%. La diferencia se debe a que ENIF capta mora autodeclarada amplia, mientras que IMOR mide cartera vencida ≥90 días en banca formal.

## 2. Métricas de desempeño del motor

| Métrica | Valor |
|---|---:|
| Accuracy | 0.6528 |
| Precision | 1.0000 |
| Recall (Sensibilidad) | 0.5517 |
| Specificity | 1.0000 |
| F1-Score | 0.7111 |
| AUC-ROC | 0.9973 |
| Costo asimétrico (4:1) | 0.3472 |

### Matriz de confusión

|  | Predicho APROBAR | Predicho RECHAZAR |
|---|---:|---:|
| **Real bueno (y=1)** | VP = 2,242 | FN = 1,822 |
| **Real malo (y=0)**  | FP = 0 | VN = 1,184 |

## 3. Comparativa contra German Credit Dataset

| Métrica | MIHAC sobre German (1994, alemán) | MIHAC sobre ENIF (2024, mexicano) | Δ |
|---|---:|---:|---:|
| Accuracy | 0.4590 | 0.6528 | +0.1938 |
| Precision | 0.7416 | 1.0000 | +0.2584 |
| Recall | 0.3486 | 0.5517 | +0.2031 |
| F1-Score | 0.4742 | 0.7111 | +0.2369 |
| Specificity | 0.7167 | 1.0000 | +0.2833 |
| AUC-ROC | 0.5512 | 0.9973 | +0.4461 |
| Costo asim. | 0.7960 | 0.3472 | -0.4488 |

## 4. Análisis de errores

**Falsos Positivos: 0** — el motor no aprobó a ningún mal pagador en el subconjunto observable. Precision = 1.000 (perfecta).

**Falsos Negativos (n=1,822)** — el motor rechazó a un buen pagador (oportunidad perdida):

- Edad promedio:    44.0 años
- Ingreso promedio: $2,997
- DTI promedio:     0.30
- Score promedio:   62.2
- Rechazados directos: 743
- Revisión manual:    1,079

## 5. Caveats metodológicos

1. **Acoplamiento feature-target.** La variable de entrada `historial_crediticio` se deriva desde los mismos `p6_3_x` que generan `y_real`. Las reglas R001 (historial Bueno → +20) y R002 (historial Malo → −25) introducen dependencia mecánica con el target. El German Credit Dataset tiene un acoplamiento análogo (A1, A3 son tanto entradas como originadores de la etiqueta). Las métricas reflejan **consistencia con la mora autodeclarada**, no capacidad predictiva pura.

2. **Sesgo de selección.** ENIF observa solo a personas con crédito ya colocado, que han pasado filtros de los originadores. El backtest no contempla a solicitantes rechazados antes del crédito.

3. **Variables imputadas.** `total_deuda_actual` y `monto_credito` son sintéticos (DTI=0.30 y medianas CNBV por propósito). `antiguedad_laboral` se deriva de p3_10 × p3_13. Estas imputaciones suprimen R011, R013, R014 y el veto DTI por diseño.

4. **Granularidad reducida.** `tipo_vivienda` colapsa Rentada/Prestada en 'Familiar'. `proposito_credito` se infiere del tipo de crédito tenido — 97.7% queda como 'Consumo' por el dominio del crédito de tienda/tarjeta en la población ENIF.

## 6. Texto para artículo académico (2 párrafos)

> **Aplicación de MIHAC sobre datos mexicanos.** Para evaluar la transferibilidad del motor heurístico, se corrió MIHAC v1.0 sobre 5,248 personas de la Encuesta Nacional de Inclusión Financiera 2024 (INEGI) con outcome de pago observable. La derivación del target se construyó a partir de la mora autodeclarada en los nueve indicadores p6_3_x del módulo de crédito; resultando en 4,064 buenos pagadores y 1,184 casos con atraso (22.6%). El motor alcanzó Accuracy=0.653, Precision=1.000, Recall=0.552, F1=0.711 y AUC-ROC=0.997 bajo la convención habitual (REVISIÓN_MANUAL contado como rechazo). La comparación contra el backtest sobre German Credit (Accuracy=0.459, AUC=0.551) muestra que las reglas heurísticas calibradas para banca alemana 1994 conservan capacidad discriminatoria moderada en el contexto mexicano contemporáneo.

> **Limitaciones y trabajo futuro.** Tres factores moderan estas conclusiones. Primero, el target y la variable `historial_crediticio` comparten origen en p6_3_x, lo que introduce un acoplamiento mecánico vía las reglas R001 y R002 — las métricas miden consistencia interna más que poder predictivo verdadero. Segundo, el monto absoluto de deuda no se captura en ENIF; la imputación con DTI=0.30 sintético desactiva por diseño tres reglas de compensación (R011, R013, R014) y el veto DTI, lo que reduce la expresividad del motor en este dataset. Tercero, ENIF observa cartera ya colocada, con sesgo de selección hacia perfiles que pasaron filtros previos. La calibración con datos CNBV (Módulo G del plan v2) y la incorporación de un modelo ML supervisado (Módulo C) son los siguientes pasos propuestos para controlar estos sesgos y elevar la capacidad discriminatoria por encima de AUC=0.70.
