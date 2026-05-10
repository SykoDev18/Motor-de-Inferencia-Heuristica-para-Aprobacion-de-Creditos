# MIHAC v1.0 — Hipótesis del Proyecto y Estrategias de Inferencia

> **Motor de Inferencia Heurística para Aprobación de Créditos**
> Formulación de la hipótesis de investigación y análisis comparativo de las estrategias de encadenamiento hacia adelante y hacia atrás.

---

## Tabla de Contenidos

1. [Hipótesis del Proyecto](#1-hipótesis-del-proyecto)
   - 1.1 [Formulación de la hipótesis](#11-formulación-de-la-hipótesis)
   - 1.2 [Variables de la hipótesis](#12-variables-de-la-hipótesis)
   - 1.3 [Criterios de verificación](#13-criterios-de-verificación)
   - 1.4 [Evidencia empírica de validación](#14-evidencia-empírica-de-validación)
2. [Estrategias de Inferencia](#2-estrategias-de-inferencia)
   - 2.1 [Forward Chaining en MIHAC (implementado)](#21-forward-chaining-en-mihac-implementado)
   - 2.2 [Backward Chaining (análisis teórico)](#22-backward-chaining-análisis-teórico)
   - 2.3 [Comparativa formal: Forward vs. Backward](#23-comparativa-formal-forward-vs-backward)
   - 2.4 [Justificación de la elección de Forward Chaining](#24-justificación-de-la-elección-de-forward-chaining)

---

## 1. Hipótesis del Proyecto

### 1.1 Formulación de la hipótesis

> **Hipótesis:**
>
> *"Un sistema basado en conocimiento con arquitectura de seis componentes canónicos (Base de Conocimiento, Motor de Inferencia, Memoria de Trabajo, Módulo de Adquisición de Conocimiento, Módulo de Explicación e Interfaz de Usuario), fundamentado en reglas heurísticas IF-THEN y un modelo de scoring ponderado de cuatro dimensiones, es capaz de automatizar la evaluación de solicitudes de crédito hipotecario con una latencia inferior a 50 ms, consistencia determinista del 100% y explicabilidad completa de cada dictamen, constituyendo una alternativa viable frente a los modelos de aprendizaje automático supervisado en contextos donde no se dispone de datos históricos etiquetados de cumplimiento/incumplimiento crediticio."*

Esta hipótesis establece **criterios cuantitativos verificables** (latencia < 50 ms, determinismo 100%) que pueden comprobarse directamente mediante los resultados de las pruebas de rendimiento y validación empírica del sistema.

### 1.2 Variables de la hipótesis

| Tipo de variable        | Variable                  | Indicador                                                    | Valor esperado                                                                   |
| :---------------------- | :------------------------ | :----------------------------------------------------------- | :------------------------------------------------------------------------------- |
| **Independiente** | Arquitectura del SBC      | 6 componentes canónicos implementados                       | BC, MI, MT, MAC, ME, IU                                                          |
| **Independiente** | Base de Conocimiento      | Reglas heurísticas formales                                 | 15 reglas IF-THEN (11 directas + 4 compensación)                                |
| **Independiente** | Modelo de scoring         | Dimensiones ponderadas                                       | 4 dimensiones: solvencia (40%), estabilidad (30%), historial (20%), perfil (10%) |
| **Dependiente**   | Latencia de evaluación   | Milisegundos por evaluación completa                        | < 50 ms                                                                          |
| **Dependiente**   | Consistencia determinista | Porcentaje de resultados idénticos ante entradas idénticas | 100%                                                                             |
| **Dependiente**   | Explicabilidad            | Trazabilidad del dictamen regla por regla                    | Completa (cada regla activada documentada)                                       |
| **Dependiente**   | Viabilidad operativa      | Throughput sostenido                                         | ≥ 100 evaluaciones/segundo                                                      |
| **Dependiente**   | Calidad del software      | Cobertura de código y tests sin fallos                      | ≥ 90% cobertura, 0 fallos                                                       |

### 1.3 Criterios de verificación

La hipótesis se considera **verificada** si se cumplen simultáneamente los siguientes criterios:

| # | Criterio                 | Métrica                                      | Umbral de aceptación                                 | Método de verificación                                                |
| :-: | :----------------------- | :-------------------------------------------- | :---------------------------------------------------- | :---------------------------------------------------------------------- |
| C1 | **Rendimiento**    | Latencia media del motor de inferencia        | < 50 ms                                               | Pruebas de carga con N=1,000 evaluaciones                               |
| C2 | **Determinismo**   | Consistencia entre instancias independientes  | 100%                                                  | 100 evaluaciones × 2 instancias con datos idénticos                   |
| C3 | **Explicabilidad** | Trazabilidad de reglas activadas por dictamen | 100% de dictámenes con reporte completo              | Verificación del Módulo de Explicación sobre 3 casos paradigmáticos |
| C4 | **Throughput**     | Evaluaciones por segundo sostenidas           | ≥ 100 evals/s                                        | Carga sostenida de 1,000 evaluaciones secuenciales                      |
| C5 | **Calidad**        | Cobertura de código + tests sin fallos       | ≥ 90% cobertura, 0 fallos                            | pytest + pytest-cov sobre suite completa                                |
| C6 | **Coherencia**     | Distribución de dictámenes en backtesting   | Distribución razonable, sin anomalías sistemáticas | Backtesting con German Credit Dataset (1,000 registros)                 |

### 1.4 Evidencia empírica de validación

Los resultados obtenidos durante el desarrollo y validación de MIHAC v1.0 verifican la hipótesis en todos los criterios establecidos:

| # | Criterio                   | Resultado obtenido                                                 | ¿Cumple? | Margen de excedencia                        |
| :-: | :------------------------- | :----------------------------------------------------------------- | :-------: | :------------------------------------------ |
| C1 | Latencia < 50 ms           | **0.41 ms**                                                  |    ✓    | 122× por debajo del umbral                 |
| C2 | Determinismo 100%          | **100%** (verificado con 100 eval × 2 instancias)           |    ✓    | Absoluto                                    |
| C3 | Explicabilidad completa    | **100%** de dictámenes con reporte en lenguaje natural      |    ✓    | Completa + 2 formatos (detallado y resumen) |
| C4 | Throughput ≥ 100 evals/s  | **2,424 evals/s**                                            |    ✓    | 24× por encima del objetivo                |
| C5 | Cobertura ≥ 90%, 0 fallos | **92.0%** cobertura, **254 tests**, **0 fallos** |    ✓    | +2 pp cobertura, +54 tests sobre mínimo    |
| C6 | Distribución coherente    | 52.1% aprobados, 39.5% rechazados, 7.4% revisión                  |    ✓    | Coherente con perfil del dataset (70/30)    |

**Conclusión:** La hipótesis se verifica empíricamente en la totalidad de los criterios definidos, con márgenes de excedencia significativos en todos los indicadores cuantitativos.

---

## 2. Estrategias de Inferencia

### 2.1 Forward Chaining en MIHAC (implementado)

MIHAC implementa **encadenamiento hacia adelante** (*forward chaining*), también denominado inferencia dirigida por datos (*data-driven*). En esta estrategia, el ciclo de razonamiento parte de los **hechos observados** (las 9 variables de entrada del solicitante) y aplica reglas cuyas precondiciones se satisfacen, generando progresivamente nuevos **hechos derivados** hasta alcanzar la conclusión final (dictamen).

```
ORIENTACIÓN:   Datos → Hechos derivados → Conclusión
PROPÓSITO:     Monitoreo y control de la evaluación crediticia
DIRECCIÓN:     De los hechos hacia las conclusiones (bottom-up)
```

#### 2.1.1 Flujo de inferencia por niveles de hechos

El proceso de forward chaining en MIHAC genera hechos en **5 niveles jerárquicos** de derivación:

|    Nivel    | Tipo de hecho                                                   | Hechos generados                                                                                                                                                    | Componente del SBC                          |
| :---------: | :-------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------ | :------------------------------------------ |
| **0** | **Hechos iniciales** (observados)                         | `edad=45`, `ingreso=35000`, `deuda=2000`, `historial=2`, `antiguedad=15`, `dependientes=1`, `vivienda=Propia`, `proposito=Negocio`, `monto=10000` | Interfaz de Usuario → Validator            |
| **1** | **Hechos derivados de 1er orden** (cálculos numéricos)  | `DTI=5.71%`, `DTI_clase=BAJO`, `solvencia=28`, `estabilidad=30`, `historial_score=20`, `perfil=10`, `score_base=88`                                   | Scorer (calculate_dti, calculate_subscores) |
| **2** | **Hechos derivados de 2do orden** (evaluación de reglas) | `R001 activada (+20)`, `R003 activada (+15)`, `R005 activada (+10)`, `R006 activada (+8)`, `R012 activada (+10)`, `impacto_total=+63`                   | Scorer (apply_rules)                        |
| **3** | **Conclusión** (dictamen formal)                         | `score_final=100`, `umbral=80`, `dictamen=APROBADO`                                                                                                           | Engine (evaluate)                           |
| **4** | **Meta-conclusión** (explicación)                       | Reporte en lenguaje natural con trazabilidad completa de las 5 reglas activadas                                                                                     | Explainer (generate)                        |

#### 2.1.2 Diagrama del forward chaining

```
    ┌─────────────────────────────────────────────────────────────┐
    │                    FORWARD CHAINING EN MIHAC                │
    │              (Encadenamiento hacia adelante)                 │
    └─────────────────────────────────────────────────────────────┘

    Nivel 0 — HECHOS INICIALES (datos del solicitante)
    ┌────────────────────────────────────────────────────────────┐
    │  edad=45  ingreso=35000  deuda=2000  historial=2          │
    │  antiguedad=15  dependientes=1  vivienda=Propia           │
    │  proposito=Negocio  monto=10000                           │
    └──────────────────────────┬─────────────────────────────────┘
                               │ sanitizar + validar (Grupos A-D)
                               ▼
    Nivel 1 — HECHOS DERIVADOS (cálculos)
    ┌────────────────────────────────────────────────────────────┐
    │  DTI = 5.71% (BAJO)                                       │
    │  Solvencia = 28/40  Estabilidad = 30/30                   │
    │  Historial = 20/20  Perfil = 10/10                        │
    │  Score base = 88                                           │
    └──────────────────────────┬─────────────────────────────────┘
                               │ evaluar 15 reglas
                               ▼
    Nivel 2 — REGLAS ACTIVADAS
    ┌────────────────────────────────────────────────────────────┐
    │  R001: HistorialBueno(x)       → +20  ✓                  │
    │  R003: EstableLab(x)           → +15  ✓                  │
    │  R005: ViviendaPropia(x)       → +10  ✓                  │
    │  R006: PropositoNegocio(x)     → +8   ✓                  │
    │  R012: Compensación solvencia  → +10  ✓                  │
    │  Impacto total: +63                                        │
    └──────────────────────────┬─────────────────────────────────┘
                               │ score + umbral + dictamen
                               ▼
    Nivel 3 — CONCLUSIÓN
    ┌────────────────────────────────────────────────────────────┐
    │  Score final = clamp(88 + 63, 0, 100) = 100               │
    │  Umbral = 80 (monto ≤ $20,000)                            │
    │  DICTAMEN: APROBADO                                        │
    └──────────────────────────┬─────────────────────────────────┘
                               │ generar explicación
                               ▼
    Nivel 4 — META-CONCLUSIÓN
    ┌────────────────────────────────────────────────────────────┐
    │  Reporte en lenguaje natural (~35 líneas) con:            │
    │  ▲ 5 factores positivos, 0 negativos, 1 compensación     │
    │  Trazabilidad completa: hechos → reglas → dictamen        │
    └────────────────────────────────────────────────────────────┘
```

#### 2.1.3 Propiedades formales del forward chaining en MIHAC

| Propiedad                          | Descripción                                                                                  | Verificación                                                                 |
| :--------------------------------- | :-------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------- |
| **Monotonía**               | Cada paso agrega hechos sin modificar los anteriores: MT₀ ⊂ MT₁ ⊂ MT₂ ⊂ ... ⊂ MT₄     | Los diccionarios de resultado se construyen progresivamente                   |
| **Exhaustividad**            | Las 15 reglas se evalúan contra todos los hechos disponibles                                 | `apply_rules()` itera sobre la totalidad de `rules.json`                  |
| **Sin backtracking**         | Una vez evaluado un paso, no se retrocede ni se reevalúa                                     | Pipeline secuencial de 9 pasos unidireccional                                 |
| **Terminación garantizada** | El pipeline tiene un número fijo de pasos (9); no hay ciclos                                 | No existen reglas que generen hechos que disparen otras reglas recursivamente |
| **Cortocircuito por DTI**    | Excepción controlada: DTI Crítico (≥ 60%) produce RECHAZADO inmediato sin evaluar el score | `∀x : DTI_Critico(x) → Dictamen(x) = RECHAZADO`                           |

#### 2.1.4 Correspondencia con el pipeline de 9 pasos

| Paso | Operación del pipeline     | Nivel de forward chaining                                 |
| :--: | :-------------------------- | :-------------------------------------------------------- |
|  1  | Sanitizar datos             | Nivel 0 → Nivel 0 (limpieza de hechos iniciales)         |
|  2  | Validar (Grupos A-D)        | Nivel 0 → Verificación de integridad                    |
|  3  | Calcular DTI                | Nivel 0 → Nivel 1 (hecho derivado: DTI)                  |
|  4  | Calcular sub-scores         | Nivel 0+1 → Nivel 1 (hechos derivados: 4 sub-scores)     |
|  5  | Evaluar reglas heurísticas | Nivel 0+1 → Nivel 2 (hechos derivados: reglas activadas) |
|  6  | Score final + dictamen      | Nivel 1+2 → Nivel 3 (conclusión)                        |
|  7  | Generar explicación        | Nivel 0+1+2+3 → Nivel 4 (meta-conclusión)               |
|  8  | Registrar en log            | Nivel 3+4 → Efecto secundario (persistencia)             |
|  9  | Actualizar estadísticas    | Nivel 3 → Efecto secundario (sesión)                    |

---

### 2.2 Backward Chaining (análisis teórico)

El **encadenamiento hacia atrás** (*backward chaining*), también denominado inferencia dirigida por objetivos (*goal-driven*), opera en dirección inversa: parte de una **hipótesis** (objetivo a verificar) y busca retroactivamente los hechos necesarios para confirmarla o refutarla.

```
ORIENTACIÓN:   Hipótesis → Buscar evidencia → Confirmar/Refutar
PROPÓSITO:     Diagnóstico y consulta
DIRECCIÓN:     De las conclusiones hacia los hechos (top-down)
```

MIHAC **no implementa** backward chaining como estrategia de inferencia, pero su análisis teórico en el dominio crediticio resulta relevante a efectos comparativos y de comprensión de las alternativas de diseño.

#### 2.2.1 Ejemplo hipotético aplicado al dominio de MIHAC

Si MIHAC utilizara backward chaining, el proceso de razonamiento para un solicitante sería:

```
    ┌─────────────────────────────────────────────────────────────┐
    │                   BACKWARD CHAINING (hipotético)            │
    │              (Encadenamiento hacia atrás)                   │
    └─────────────────────────────────────────────────────────────┘

    OBJETIVO: ¿El solicitante merece dictamen APROBADO?
    ┌────────────────────────────────────────────────────────────┐
    │  Hipótesis: Dictamen(x) = APROBADO                        │
    └──────────────────────────┬─────────────────────────────────┘
                               │ ¿Qué se necesita?
                               ▼
    SUB-OBJETIVO 1: ¿DTI no es CRITICO?
    ┌────────────────────────────────────────────────────────────┐
    │  Necesito: DTI(x) < 0.60                                  │
    │  Necesito: deuda(x) e ingreso(x)                          │
    │  → PREGUNTAR al solicitante: ¿cuál es su deuda e ingreso? │
    │  → Verificar: DTI = 2000/35000 = 5.71% < 60%  ✓          │
    └──────────────────────────┬─────────────────────────────────┘
                               │ sub-objetivo cumplido
                               ▼
    SUB-OBJETIVO 2: ¿Score ≥ umbral (80)?
    ┌────────────────────────────────────────────────────────────┐
    │  Necesito: score_final ≥ 80                                │
    │  → ¿Qué reglas positivas pueden activarse?                 │
    │  → R001 (+20): ¿historial = 2? → PREGUNTAR → Sí ✓        │
    │  → R003 (+15): ¿antigüedad ≥ 5? → PREGUNTAR → Sí ✓      │
    │  → R005 (+10): ¿vivienda = Propia? → PREGUNTAR → Sí ✓    │
    │  → ¿Es suficiente? → Calcular score... → Sí ✓             │
    └──────────────────────────┬─────────────────────────────────┘
                               │ ambos sub-objetivos cumplidos
                               ▼
    CONCLUSIÓN: Hipótesis CONFIRMADA → APROBADO
    ┌────────────────────────────────────────────────────────────┐
    │  Solo se consultaron las reglas y hechos necesarios        │
    │  para confirmar la hipótesis.                              │
    │  Reglas no relevantes (R008, R009, R010...) NO se          │
    │  evaluaron → mayor eficiencia, menor exhaustividad.        │
    └────────────────────────────────────────────────────────────┘
```

#### 2.2.2 Aplicación natural del backward chaining: diagnóstico post-dictamen

Aunque MIHAC no usa backward chaining para inferir el dictamen, la estrategia sería natural para un escenario de **consulta diagnóstica**:

| Escenario                         | Pregunta (backward chaining)                              | Proceso                                                                                                                           |
| :-------------------------------- | :-------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------- |
| **Reclamación de rechazo** | *"¿Por qué fue rechazado el solicitante X?"*          | Partir de RECHAZADO → buscar qué reglas negativas se activaron → rastrear qué hechos las dispararon                           |
| **Asesoría pre-solicitud** | *"¿Qué necesita este solicitante para ser aprobado?"* | Partir de APROBADO → identificar qué condiciones faltan → sugerir mejoras concretas                                            |
| **Auditoría regulatoria**  | *"¿Fue correcto el rechazo del caso #4521?"*           | Partir del dictamen registrado → verificar que las reglas activadas corresponden a los hechos → confirmar o detectar anomalías |
| **Calibración de reglas**  | *"¿Qué ajuste reduciría los falsos negativos?"*      | Partir de casos FN → buscar qué reglas o umbrales causaron el rechazo incorrecto → proponer ajustes                            |

---

### 2.3 Comparativa formal: Forward vs. Backward

| Criterio                                     | Forward Chaining (MIHAC ✓)                                                                   | Backward Chaining (no implementado)                                                            |
| :------------------------------------------- | :-------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------- |
| **Orientación**                       | A los**datos** (*data-driven*)                                                        | A los **objetivos** (*goal-driven*)                                                   |
| **Punto de partida**                   | 9 variables de entrada del solicitante                                                        | Hipótesis: "¿APROBADO? ¿RECHAZADO?"                                                         |
| **Dirección del razonamiento**        | Hechos → Reglas → Conclusión (*bottom-up*)                                               | Conclusión → Reglas → ¿Qué hechos necesito? (*top-down*)                                |
| **Pregunta que responde**              | *"Dado este solicitante, ¿cuál es el dictamen?"*                                          | *"Para aprobar a este solicitante, ¿qué condiciones debe cumplir?"*                        |
| **Aplicación típica**                | **Monitoreo y control** — evaluar cada solicitud que llega                             | **Diagnóstico y consulta** — investigar por qué fue rechazado                         |
| **Exploración del espacio de reglas** | **Exhaustiva**: evalúa las 15 reglas para cada solicitante                             | **Selectiva**: solo explora las reglas relevantes para la hipótesis                     |
| **Eficiencia computacional**           | Puede evaluar reglas no relevantes para el dictamen final                                     | Potencialmente más eficiente si el objetivo está claro                                       |
| **Exhaustividad del resultado**        | **Total**: se conocen todas las reglas activadas (positivas, negativas, compensaciones) | **Parcial**: solo se conocen las reglas suficientes para confirmar/refutar la hipótesis |
| **Requisito de datos iniciales**       | **Todos los datos disponibles desde el inicio**                                         | Puede operar con datos parciales, solicitando los faltantes                                    |
| **Cuándo es más adecuado**           | Cuando se tienen todos los datos y se desconoce la conclusión                                | Cuando se tiene una hipótesis específica que verificar                                       |
| **Idoneidad para explicabilidad**      | Alta — el reporte incluye todas las reglas evaluadas                                         | Media — el reporte solo incluye las reglas consultadas                                        |
| **Uso en MIHAC**                       | Pipeline de 9 pasos del Motor de Inferencia                                                   | El Módulo de Explicación realiza una forma*implícita* de rastreo retroactivo              |

---

### 2.4 Justificación de la elección de Forward Chaining

La selección de encadenamiento hacia adelante como estrategia de inferencia de MIHAC se fundamenta en tres razones técnicas alineadas con las propiedades requeridas del dominio:

#### Razón 1: El objetivo no es único ni conocido de antemano

En backward chaining se parte de una hipótesis concreta (e.g., "¿es APROBADO?") y se busca evidencia para confirmarla. En MIHAC, el sistema debe **descubrir** cuál de los 3 dictámenes posibles (APROBADO, REVISIÓN MANUAL, RECHAZADO) corresponde al solicitante. No existe una hipótesis previa que verificar — el dictamen es el resultado del razonamiento, no su punto de partida.

```
Forward (MIHAC):   datos del solicitante  →  ???  →  descubrir dictamen
Backward:          "¿es APROBADO?"        →  buscar evidencia  →  confirmar/refutar
```

#### Razón 2: Todos los datos están disponibles desde el inicio

El solicitante proporciona las 9 variables completas al llenar el formulario web (Interfaz de Usuario). No existe la necesidad de "ir a buscar" datos adicionales para confirmar una hipótesis, que es la fortaleza típica del backward chaining en sistemas de diagnóstico médico o consulta interactiva.

```
Forward (MIHAC):   9 variables completas → procesar → dictamen
Backward:          hipótesis → ¿edad? (preguntar) → ¿ingreso? (preguntar) → ...
```

#### Razón 3: Se requiere evaluación exhaustiva para explicabilidad completa

Para generar el reporte de explicación completo — que categoriza factores positivos (▲), negativos (▼) y compensaciones (⟳) — es necesario evaluar **todas** las 15 reglas, no solo las que apoyan un dictamen particular. Forward chaining garantiza esta exhaustividad de forma natural.

```
Forward (MIHAC):   15 reglas evaluadas → reporte con TODOS los factores
Backward:          solo las reglas relevantes para la hipótesis → reporte PARCIAL
```

Esta propiedad es crítica para el cumplimiento regulatorio: la CNBV y la Ley FinTech requieren que el solicitante conozca **todas** las razones que influyeron en la decisión, no solo las que la causaron directamente.

#### Nota sobre el razonamiento retroactivo implícito

Si bien el Motor de Inferencia opera exclusivamente mediante forward chaining, el **Módulo de Explicación** realiza una forma *implícita* de razonamiento retroactivo cuando categoriza post-hoc las reglas activadas según su contribución al dictamen. Sin embargo, esto constituye **post-procesamiento del resultado** (formateo para presentación), no una estrategia de inferencia propiamente dicha. El mecanismo formal de inferencia del sistema es y permanece forward chaining.

---

*MIHAC v1.0 — Hipótesis y Estrategias de Inferencia © 2026*

*Universidad Autónoma del Estado de Hidalgo — Escuela Superior de Tlahuelilpan — Licenciatura en Ingeniería de Software*
