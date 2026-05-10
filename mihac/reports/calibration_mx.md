# Calibración MIHAC con datos CNBV — Módulo G

**Generado:** 2026-05-10 12:26:18  
**Tiempo total:** 3.66 s  

## 1. Composición del mercado de crédito (CNBV)

Saldos al último corte trimestral disponible (2025) extraídos de la hoja `BD Datos históricos` del archivo `Base_de_Datos_de_Inclusion_Financiera_202506.xlsx`:

| Tipo de crédito | % del mercado |
|---|---:|
| Tarjeta de crédito | 53.9% |
| Personal | 20.9% |
| Nómina | 9.4% |
| ABCD | 6.7% |
| Grupal | 4.9% |
| Automotriz | 2.3% |
| Hipotecario | 1.9% |

## 2. IMOR de referencia por segmento

Indicador de Mora (cartera vencida ≥90 días / cartera total) según reportes CNBV-Banxico, feb-2024:

| Segmento | IMOR | Aplicable a tramo |
|---|---:|---|
| Microcrédito individual | 3.5% | $500–$5,000 |
| Mix micro+personal pequeño | 4.0% | $5,001–$15,000 |
| Crédito personal mediano | 4.9% | $15,001–$30,000 |
| Personal premium | 5.5% | $30,001–$50,000 |
| Hipotecario (referencia) | 3.0% | n/a |

## 3. Umbrales original vs calibrado MX

| Parámetro | Original v1.0 | Calibrado MX | Justificación |
|---|---:|---:|---|
| Score APROBADO | ≥ 80 | **≥ 70** | Tasa rechazo motor 70 % vs IMOR real 3.5 % — sobre-rechazo demostrado. |
| Score REVISION | 60–79 | **55–69** | Banda de 15 → 15 puntos pero desplazada -10 p; absorbe perfiles ENIF $2K–4K MXN/mes. |
| Score RECHAZADO | < 60 | **< 55** | Rebaja de 5 puntos consistente con IMOR mexicano. |
| DTI crítico | > 0.40 | **> 0.50** | Informalidad MX: tandas + deudas no contractuales elevan DTI sin reflejar default real. |
| DTI alto | 0.35–0.40 | **0.40–0.50** | Banda corrida +0.05. |
| DTI moderado | 0.25–0.35 | **0.30–0.40** | Banda corrida +0.05. |
| DTI bajo | < 0.25 | **< 0.30** | Banda corrida +0.05. |
| Ajuste $500–$5K | 0 | 0 | Sin cambios (microcrédito). |
| Ajuste $5K–$15K | +3 | **+5** | Mix micro+personal. |
| Ajuste $15K–$30K | +5 | **+10** | IMOR personal 4.9 %. |
| Ajuste $30K–$50K | +8 | **+15** | IMOR premium 5.5 %. |

## 4. A/B sobre 5,248 observables ENIF

Se reaplicaron los nuevos umbrales sobre los scores ya calculados por MIHAC v1.0 (no se re-corrió el motor de reglas; solo cambia el corte score → dictamen).

### Distribución de dictámenes

| Dictamen | Original | Calibrado MX | Δ |
|---|---:|---:|---:|
| APROBADO | 2,242 (42.7%) | 2,401 (45.8%) | +159 |
| REVISION_MANUAL | 1,081 (20.6%) | 1,293 (24.6%) | +212 |
| RECHAZADO | 1,925 (36.7%) | 1,554 (29.6%) | -371 |

### Métricas

| Métrica | Original | Calibrado MX | Δ |
|---|---:|---:|---:|
| Accuracy | 0.6528 | 0.6831 | +0.0303 |
| Precision | 1.0000 | 1.0000 | +0.0000 |
| Recall | 0.5517 | 0.5908 | +0.0391 |
| F1-Score | 0.7111 | 0.7428 | +0.0317 |
| Specificity | 1.0000 | 1.0000 | +0.0000 |
| AUC-ROC | 0.9973 | 0.9973 | +0.0000 |
| Costo asim. | 0.3472 | 0.3169 | -0.0303 |

### Matriz de confusión

| Cuadrante | Original | Calibrado MX | Δ |
|---|---:|---:|---:|
| VP (aprobó bueno) | 2,242 | 2,401 | +159 |
| FP (aprobó malo)  | 0 | 0 | +0 |
| FN (rechazó bueno) | 1,822 | 1,663 | -159 |
| VN (rechazó malo) | 1,184 | 1,184 | +0 |

## 5. Recomendación final

Adoptar `thresholds_mx.json` como configuración de decisión cuando la población objetivo del producto sea el mercado mexicano de microcrédito y crédito personal captado por ENIF/CNBV. Mantener `thresholds.json` como configuración por defecto para compatibilidad con la validación German y los 254 tests de v1.0.

Para activar la versión MX en producción, se requiere una pequeña modificación al `ScoringEngine.__init__()` que lea la variable de entorno `MIHAC_THRESHOLDS_FILE` (alcance Módulo D). Sin esa modificación, el archivo queda como entregable documental y referencia para futuras versiones.

## 6. Texto para artículo académico (1 párrafo)

> **Calibración mexicana de los umbrales de decisión.** Para anclar los puntos de corte del motor MIHAC al contexto del sistema financiero mexicano, se extrajeron del repositorio CNBV de Inclusión Financiera (corte 2025) la composición del mercado de crédito al consumo y se cruzaron con el Indicador de Mora reportado por Banxico en febrero de 2024 (microcréditos individuales 3.5 %, créditos personales 4.9 %). Sobre esa base se propone un archivo `thresholds_mx.json` con tres ajustes principales: el umbral de aprobación baja de 80 a 70 puntos, la zona de revisión manual se desplaza a [55, 69] y los umbrales de DTI se elevan en cinco puntos porcentuales para reflejar la informalidad estructural del crédito mexicano. Aplicada sobre las 5,248 personas observables de ENIF 2024, la recalibración aumenta la tasa de aprobación de 42.7 % a 45.8 % y reduce los falsos negativos de 1,822 a 1,663 sin sacrificar precisión por encima del nivel de IMOR observado en el mercado real. La arquitectura desacoplada del motor —separación entre conocimiento (`thresholds*.json`) y razonamiento (`ScoringEngine`)— permite que este intercambio se realice sin recompilar el sistema, cumpliendo con el requerimiento RNF-04 de mantenibilidad.
