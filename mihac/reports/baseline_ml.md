# Modelos ML baseline sobre ENIF 2024 — Módulo C

**Generado:** 2026-05-10 11:56:25  
**Población observable:** 5,248 filas  
**Tiempo total:** 209.2 s  

## 0. Hallazgo principal (TL;DR)

En el subconjunto observable, `historial_crediticio` y `y_real` están **perfectamente
acoplados** (cross-tab diagonal: 1,184 historial=0 ↔ y=0; 4,064 historial=2 ↔ y=1; 0
desalineados). Esto se sigue mecánicamente de cómo se derivan ambas variables a partir
de los mismos `p6_3_x` de ENIF.

**Consecuencias medidas:**

- Cualquier ML con historial alcanza AUC = 1.000 trivialmente.
- Sin historial, los 3 modelos caen a AUC ≈ 0.56 (apenas mejor que azar).
- MIHAC con historial alcanza AUC = 0.997, **pero por la misma razón**: las reglas
  R001/R002 codifican el target.

**Implicación:** sobre ENIF 2024 con outcome derivado de `p6_3_x`, ni MIHAC ni un ML
supervisado pueden demostrar capacidad predictiva real con las features actuales.
La señal está casi en su totalidad en historial. Las otras 8 features aportan
≈ 0.06 de AUC sobre el azar (0.56 − 0.50). Esto motiva fuertemente:

1. **Módulo G (calibración con CNBV)** antes que Módulo D — necesitamos un target
   independiente de `p6_3_x` (p.ej. mora ex-post a 90 días desde Buró), no
   autodeclarada.
2. **Replanteo de features** para captar señales no-circulares: gasto vs ingreso,
   estabilidad de domicilio, comportamiento de ahorro (`p5_x`), uso responsable
   del crédito (`p4_6_x`).

## 1. Tabla comparativa definitiva (escenario A)

Las 9 features MIHAC se usan tanto en MIHAC como en los 3 modelos ML — comparación apples-to-apples.

| Modelo | Accuracy | F1 | AUC-ROC | Explicabilidad | Latencia |
|---|---:|---:|---:|:---:|---:|
| **MIHAC (reglas)** | 0.653 | 0.711 | 0.997 | 100% (15 reglas IF-THEN) | ~0.4 ms |
| Logistic Regression (L1) | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | Coeficientes (parcial) | 7.00 ms |
| Random Forest | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | SHAP | 76.75 ms |
| Gradient Boosting | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | SHAP | 7.36 ms |

*Métricas ML reportadas como mean ± std sobre StratifiedKFold(n_splits=5, shuffle=True, random_state=42).*

## 2. Sensibilidad al data leakage (escenario B)

Se reentrena cada modelo eliminando `historial_crediticio` (la feature acoplada al target). La caída en métricas refleja cuánto del desempeño venía del leakage.

| Modelo | Acc (sin hist) | F1 (sin hist) | AUC (sin hist) | Δ AUC vs A |
|---|---:|---:|---:|---:|
| Logistic Regression (L1) | 0.774 ± 0.000 | 0.873 ± 0.000 | 0.556 ± 0.014 | -0.444 |
| Random Forest | 0.775 ± 0.000 | 0.873 ± 0.000 | 0.567 ± 0.025 | -0.433 |
| Gradient Boosting | 0.775 ± 0.002 | 0.873 ± 0.001 | 0.566 ± 0.033 | -0.434 |

## 3. Análisis de trade-offs

- **MIHAC** tiene Precision = 1.000 y Recall = 0.55 sobre observables: solo aprueba
  cuando `historial == 2` (regla R001 +20). Es el rincón más conservador del espacio
  de decisión y rechaza al 45 % de los buenos pagadores (FN = 1,822) — todos con
  ingresos < $3,000 MXN/mes. Su AUC = 0.997 refleja consistencia mecánica con el
  target, no capacidad predictiva.
- **Los 3 modelos ML con historial** alcanzan métricas perfectas (1.000) por
  separación lineal trivial entre las 2 clases — el solver de scikit-learn detecta
  que historial sola separa 100 % del target. La igualdad entre LR, RF y GB confirma
  que ningún modelo agrega información por encima del split obvio.
- **Sin historial** (escenario B), los 3 modelos convergen a AUC ≈ 0.56 ± 0.03,
  compatible con un dataset donde las features restantes (edad, ingreso imputado,
  deuda sintética, antigüedad derivada, dependientes, vivienda binaria, propósito
  homogéneo, monto fijo por propósito) tienen poca señal individual para
  discriminar buen vs mal pagador.
- **Trade-off explicabilidad ↔ desempeño:** MIHAC es 100 % auditable regla por
  regla; los árboles requieren SHAP; LR con L1 ofrece interpretabilidad vía
  coeficientes no-cero. Pero como el desempeño verdadero es ≈ 0.56 AUC en todos
  los modelos, la elección debe priorizar **costo de implementación + auditoría
  regulatoria**, no AUC. Esto favorece a MIHAC.
- **Latencia:** MIHAC ~0.4 ms/fila; LR/GB 7 ms/fila; RF 77 ms/fila por sus 200
  árboles. Todas son aceptables para un endpoint REST de evaluación individual.

## 4. Implicación para Módulo D (motor híbrido)

**Decisión: posponer Módulo D y priorizar Módulo G.**

El criterio de éxito del Módulo C (tabla comparativa con datos reales) se cumplió,
pero **el hallazgo invalida la motivación de un motor híbrido sobre ENIF**. Con
ΔAUC = −0.43 al eliminar historial, los modelos ML no aportan capacidad
discriminatoria por encima de la que ya tiene MIHAC con sus reglas R001/R002.
Avanzar al Módulo D sin antes resolver el problema del target sería construir
una arquitectura compleja sobre datos que no soportan la comparación.

**Plan revisado:**

1. **Módulo G primero** — calibrar umbrales con datos CNBV (cartera vencida ≥ 90
   días, IMOR por segmento) o un dataset complementario (Kaggle Mexican Credit Risk,
   datos sintéticos validados con FINDEX). Necesitamos un target independiente de
   `p6_3_x` para medir capacidad predictiva real.
2. **Refinamiento de features** — explorar variables no-circulares en ENIF: salud
   financiera ENSAFI (`p4_6_x`, `p4_8_x`), comportamiento de ahorro (`p5_1_x`,
   `p5_8_x`), acceso a productos formales vs informales.
3. **Módulo D después** — solo si tras G se observa AUC sin historial > 0.70 con
   target ex-post. En ese escenario, la combinación reglas + ML sí aportaría valor.

## 5. Texto para artículo académico (1 párrafo)

> **Modelos baseline ML y diagnóstico de circularidad.** Para situar el desempeño
> de MIHAC contra alternativas estadísticas, se entrenaron Logistic Regression con
> regularización L1, Random Forest (max_depth=5) y Gradient Boosting (max_depth=3)
> con validación cruzada estratificada de 5 folds sobre las mismas 5,248 personas
> observables de ENIF 2024. Los tres modelos alcanzaron Accuracy=1.000, F1=1.000 y
> AUC-ROC=1.000 — un resultado que, lejos de validar el enfoque ML, evidencia un
> acoplamiento perfecto entre la feature `historial_crediticio` y el target
> `y_real` (cross-tab diagonal: 1,184 ↔ 0 y 4,064 ↔ 1, sin desalineación). Una
> ablación eliminando esa feature confirmó la hipótesis: los tres modelos cayeron
> a AUC ≈ 0.56 (ΔAUC = −0.44), apenas sobre el azar. La señal predictiva real
> contenida en las ocho features restantes (edad, ingreso, deuda imputada,
> antigüedad derivada, dependientes, vivienda, propósito y monto sintético) es
> mínima en el subconjunto ENIF observable. Esta evidencia motiva, antes de
> avanzar a un motor híbrido reglas-más-ML (Módulo D del plan v2), una etapa
> intermedia de calibración con datos CNBV ex-post y de exploración de features
> no-circulares en los módulos ENIF de salud financiera y comportamiento de
> ahorro.
