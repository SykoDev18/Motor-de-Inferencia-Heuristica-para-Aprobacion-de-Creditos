# MIHAC v2.0 — Mejoras, Datasets Mexicanos y Rediseño Estético

**Versión actual:** v1.0 (Sistema Experto · Flask · SQLite · Bootstrap 4)  
**Propuesta:** v2.0 (Sistema Híbrido · API REST · PostgreSQL · Tailwind CSS)  
**Fecha:** Mayo 2026

---

## PARTE I — MEJORAS FUNCIONALES DEL SISTEMA

### 1. Motor de Inferencia Híbrido (Reglas + ML)

**Problema actual:** Las 15 reglas son estáticas. No aprenden de resultados reales.

**Solución:** Dos modelos ejecutándose en paralelo con árbitro.

```
Solicitud → [Motor de Reglas v1.0] → Score_Reglas
           [Modelo ML Calibrado ] → Prob_Pago
                    ↓
             [Árbitro Inteligente]
                    ↓
        Dictamen + Confianza + Explicación
```

**Lógica del árbitro:**
- Ambos coinciden → usar reglas (más rápido, 100% explicable)
- Solo ML confiante (>85%) → usar ML + explicación SHAP
- Discrepan → REVISIÓN_MANUAL automática
- Escenario crítico (DTI >60%) → veto de reglas siempre prevalece

**Beneficio:** Accuracy esperado sube de 73% → 81-85% con datos reales de producción.

---

### 2. Calibración Automática de Pesos con Datos Reales

**Problema actual:** Los pesos (+20, -25, +15...) son heurísticos manuales.

**Solución:** Calibración periódica con resultados de pagos reales.

```python
class RuleWeightCalibrator:
    def calibrate_from_outcomes(self, evaluaciones_con_resultado):
        """
        Cada 3 meses, revisar qué reglas predijeron correctamente.
        Ajustar pesos según evidencia empírica.
        """
        for rule_id in self.rules:
            activaciones = self._get_activations(evaluaciones_con_resultado, rule_id)
            
            if len(activaciones) < 30:
                continue  # Sin evidencia suficiente
            
            accuracy_real = self._calculate_accuracy(activaciones)
            accuracy_esperada = 0.70  # Baseline
            
            if accuracy_real < 0.50:
                # Regla contraproducente → reducir peso
                self.rules[rule_id]['impacto_puntos'] *= 0.75
                
            elif accuracy_real > 0.85:
                # Regla muy confiable → aumentar peso
                self.rules[rule_id]['impacto_puntos'] *= 1.15
```

**Ciclo:** Cada 3 meses (trimestral), con al menos 300 evaluaciones con outcome real.

---

### 3. Reglas Contextuales Dinámicas

**Problema actual:** Las mismas reglas aplican para un microcrédito de $2,000 y uno de $50,000.

**Solución:** Archivos de modificadores por contexto.

```json
// modifiers.json
{
  "by_amount": {
    "micro": { "range": [0, 5000], "threshold_approval": 70 },
    "small": { "range": [5000, 15000], "threshold_approval": 80 },
    "medium": { "range": [15000, 50000], "threshold_approval": 85 }
  },
  "by_purpose": {
    "Negocio": { "R006_multiplier": 1.5, "dti_tolerance": 0.45 },
    "Educacion": { "R007_multiplier": 1.3, "youth_penalty_reduction": 0.5 },
    "Emergencia": { "threshold_reduction": 5 },
    "Vacaciones": { "R008_multiplier": 1.2 }
  },
  "macroeconomic": {
    "high_unemployment": {
      "trigger": "desempleo > 0.08",
      "R003_multiplier": 1.2,
      "R004_multiplier": 1.3
    }
  }
}
```

**Beneficio:** Umbrales más justos según el tipo de crédito solicitado.

---

### 4. API REST Completa con Documentación OpenAPI

**Problema actual:** Solo interfaz web Flask con templates HTML.

**Nuevos endpoints:**

```
POST /api/v2/evaluate          → Evaluar solicitud individual
POST /api/v2/evaluate/batch    → Evaluar hasta 100 en lote
GET  /api/v2/history           → Historial de evaluaciones
GET  /api/v2/monitoring/stats  → Métricas de los últimos 30 días
GET  /api/v2/rules             → Ver reglas activas (con autenticación)
GET  /api/docs                 → Swagger UI interactivo
```

**Respuesta enriquecida v2:**
```json
{
  "request_id": "eval_2026_05_07_1247",
  "timestamp": "2026-05-07T14:32:00",
  "dictamen": "APROBADO",
  "score_reglas": 82,
  "prob_pago_ml": 0.78,
  "confidence": 0.85,
  "metodo_principal": "consensus",
  "explicacion_texto": "...",
  "explicacion_visual_url": "/api/v2/charts/eval_2026_05_07_1247",
  "reglas_activadas": [...],
  "tiempo_evaluacion_ms": 0.52,
  "version_motor": "2.0.1"
}
```

---

### 5. Explicabilidad Visual (Waterfall + Radar)

**Problema actual:** Explicación solo en párrafo de texto plano.

**Nuevo:** Dos gráficos generados automáticamente por Plotly.

- **Waterfall chart:** Muestra cómo se construyó el score paso a paso
- **Radar chart:** Perfil del solicitante en 4 dimensiones vs. promedio de aprobados

```python
def generate_explanation_charts(resultado):
    waterfall = create_waterfall(
        base=resultado['score_base'],
        contributions=resultado['reglas_activadas']
    )
    
    radar = create_radar(
        sub_scores=resultado['sub_scores'],
        benchmark=AVERAGE_APPROVED_PROFILE
    )
    
    return {
        'waterfall_html': waterfall.to_html(),
        'radar_html': radar.to_html()
    }
```

---

### 6. Módulo de Monitoreo y Drift Detection

**Problema actual:** No hay monitoreo de producción.

**Nuevo módulo:**

```python
class DriftMonitor:
    def weekly_check(self, recent_data):
        """Ejecutar cada semana en producción."""
        
        for variable in ['ingreso_mensual', 'total_deuda_actual', 'edad']:
            p_valor = ks_test(self.baseline[variable], recent_data[variable])
            
            if p_valor < 0.05:
                self.send_alert(
                    f"⚠️ DRIFT DETECTADO en {variable} (p={p_valor:.4f}). "
                    f"Revisar umbrales de reglas."
                )
        
        # Revisar tasa de aprobación
        approval_rate = recent_data['dictamen'].value_counts(normalize=True)['APROBADO']
        if abs(approval_rate - self.baseline_approval_rate) > 0.10:
            self.send_alert(
                f"⚠️ Tasa de aprobación cambió de "
                f"{self.baseline_approval_rate:.1%} a {approval_rate:.1%}"
            )
```

---

### 7. Modo Batch + Reportes Automatizados

**Problema actual:** Solo una evaluación a la vez.

**Nuevo:** Subir CSV con múltiples solicitudes → recibir CSV con dictámenes y PDF por lote.

Casos de uso reales:
- Cooperativa financiera evalúa 200 solicitudes semanales
- Microfinanciera revisa cartera existente mensualmente
- Institución educativa evalúa créditos de becas por lote

---

## PARTE II — DATASETS MEXICANOS REALES

### Criterios para Elegir un Dataset

| Criterio | Descripción |
|----------|-------------|
| **Relevancia** | Variables similares a las 9 que usa MIHAC |
| **Accesibilidad** | Descargable sin costo |
| **Actualidad** | 2021 o más reciente |
| **Tamaño** | Al menos 1,000 registros |
| **Variables clave** | Ingreso, deuda, historial, edad, crédito |

---

### Opción 1 — ENIF 2024 ⭐ RECOMENDADA PRINCIPAL

**Fuente:** INEGI + CNBV  
**Fecha:** Publicada en marzo 2025 (levantamiento: junio-agosto 2024)  
**Registros:** ~15,263 hogares entrevistados  
**Descarga:** https://www.inegi.org.mx/programas/enif/2024/

**Variables relevantes para MIHAC:**
- Tenencia de productos de crédito formal
- Monto del último crédito solicitado
- Historial crediticio (pagos al corriente/mora)
- Ingreso mensual del hogar
- Tipo de vivienda (propia, rentada, etc.)
- Edad del informante
- Número de dependientes
- Propósito del crédito (consumo, negocio, emergencia)

**Hallazgos clave de la ENIF 2024 publicados:**
- 76.5% de adultos mexicanos tienen al menos un producto financiero
- 38% de la población tiene crédito formal
- Región noreste: mayor acceso (46.2% con crédito)
- Región sur: menor acceso (solo 67.7% con producto financiero)

**Cómo usarlo en MIHAC:**
```python
# Mapear variables ENIF → formato MIHAC
def map_enif_to_mihac(fila_enif):
    return {
        'edad': fila_enif['P_EDAD'],
        'ingreso_mensual': fila_enif['INGRESO_MENSUAL'],
        'historial_crediticio': map_historial(fila_enif['P_HIST_CRED']),
        'tipo_vivienda': map_vivienda(fila_enif['P_VIVIENDA']),
        'proposito_credito': map_proposito(fila_enif['P_PROPOSITO']),
        'numero_dependientes': fila_enif['P_DEPENDIENTES'],
        # Variables que habría que derivar:
        'total_deuda_actual': calcular_deuda(fila_enif),
        'monto_credito': fila_enif['P_MONTO_CRED'],
        'antiguedad_laboral': fila_enif['P_ANTIG_LABORAL']
    }
```

**Ventaja única:** Es el dataset mexicano más completo y oficial sobre comportamiento crediticio actual (2024). Comparable directamente con el German Credit Dataset pero con contexto mexicano.

---

### Opción 2 — ENSAFI 2023 ⭐ RECOMENDADA SECUNDARIA

**Fuente:** CONDUSEF + INEGI  
**Fecha:** Primera edición 2023, publicada 2024  
**Descarga:** https://www.inegi.org.mx/rnm/index.php/catalog/992  
**Acceso directo:** https://ensafi.condusef.gob.mx/

**Variables relevantes para MIHAC:**
- Nivel de deuda actual (bajo/medio/alto/crítico)
- Capacidad de ahorro
- Comportamiento de pago
- Nivel de estrés financiero
- Resiliencia financiera (fondo de emergencia)
- Control del presupuesto
- Acceso a crédito formal vs informal

**Hallazgos clave:**
- Solo 18% de mexicanos tiene alto nivel de salud financiera
- 37% de la población tiene alto nivel de estrés financiero
- 52% tiene algún tipo de ahorro

**Por qué es valioso para MIHAC:**
La ENSAFI mide directamente los **4 pilares del bienestar financiero** (control, seguridad, resiliencia, libertad) que son exactamente las dimensiones que MIHAC intenta evaluar con sus reglas.

**Propuesta de alineación:**

| Pilar ENSAFI | Variable MIHAC equivalente |
|-------------|---------------------------|
| Seguridad | `total_deuda_actual`, DTI ratio |
| Resiliencia | `tipo_vivienda`, capacidad de ahorro |
| Control | `historial_crediticio`, comportamiento de pago |
| Libertad | `ingreso_mensual`, estabilidad laboral |

---

### Opción 3 — CNBV: Indicadores de Microcréditos 2024

**Fuente:** Comisión Nacional Bancaria y de Valores  
**Fecha:** Actualización mensual (disponible a febrero 2024)  
**URL:** https://www.cnbv.gob.mx/Inclusi%C3%B3n/  
**Datos de Cartera:** https://datos.gob.mx/busca/dataset/cnbv

**Variables relevantes:**
- Saldo por tipo de crédito (personal, microcrédito individual, microcrédito grupal)
- Índice de Morosidad (IMOR) por tipo: personales 4.9%, microcréditos 3.5%
- Crecimiento real de cartera: microcréditos +15.6% anual
- Número de acreditados por entidad financiera
- Cartera vigente vs. vencida por segmento

**Por qué importa:**
Puedes **calibrar los umbrales de MIHAC** con los datos reales de mora del sistema financiero mexicano. Por ejemplo:

```python
# Los datos CNBV muestran que microcréditos tienen IMOR de 3.5%
# Eso significa que el ~96.5% paga a tiempo
# → El umbral de aprobación de MIHAC (80 puntos) es correcto
# → El umbral de rechazo podría ajustarse

IMOR_MICROCREDITOS_MX = 0.035  # 3.5% tasa de mora real CNBV 2024
IMOR_PERSONALES_MX = 0.049    # 4.9% créditos personales

# Calibrar umbrales según contexto real mexicano
def calibrate_thresholds_from_cnbv():
    if IMOR_MICROCREDITOS_MX < 0.04:
        # Cartera sana → podemos ser un poco más flexibles
        return {'umbral_aprobacion': 78, 'umbral_rechazo': 45}
    else:
        # Deterioro de cartera → más restrictivos
        return {'umbral_aprobacion': 82, 'umbral_rechazo': 50}
```

---

### Opción 4 — ENIGH 2022 (Variables de Hogares)

**Fuente:** INEGI  
**Fecha:** 2022 (levantamiento cada 2 años; próxima edición: 2024)  
**Descarga:** https://www.inegi.org.mx/programas/enigh/nc/2022/  
**Registros:** ~90,000 hogares

**Variables relevantes para MIHAC:**
- Ingreso corriente total por hogar
- Gasto en deudas/préstamos
- Número de integrantes del hogar
- Tipo de vivienda y tenencia
- Escolaridad del jefe de hogar (proxy de estabilidad)
- Actividad económica (proxy de antigüedad laboral)

**Limitación:** No tiene historial crediticio directo, habría que derivarlo.

**Fortaleza:** El dataset más grande disponible (~90,000 hogares) con representatividad nacional.

---

### Opción 5 — Kaggle: Mexico Financial Inclusion

**Fuente:** Comunidad Kaggle / World Bank FINDEX  
**URL:** https://www.kaggle.com/datasets?tags=16584-Mexico  
**Variables:** Acceso a cuenta bancaria, crédito, ahorro, pagos digitales por país

**Limitación:** No tiene nivel de granularidad individual suficiente para MIHAC.  
**Uso recomendado:** Análisis complementario de contexto, no como dataset de entrenamiento principal.

---

### Comparativa de Datasets

| Dataset | Año | Registros | Variables clave MIHAC | Descargable | Dificultad |
|---------|-----|-----------|----------------------|-------------|------------|
| **ENIF 2024** | 2024 | ~15,263 | 8/9 variables | ✅ Gratis | Media |
| **ENSAFI 2023** | 2023 | ~20,000+ | 6/9 variables | ✅ Gratis | Baja |
| **CNBV Microcréditos** | 2024 | Series temporales | 4/9 (agregado) | ✅ Gratis | Baja |
| **ENIGH 2022** | 2022 | ~90,000 | 5/9 variables | ✅ Gratis | Alta |
| **Kaggle Mexico** | Varios | Variable | 3/9 variables | ✅ Gratis | Baja |

---

### Plan de Uso de Datasets en MIHAC v2.0

#### Fase 1: Validación (inmediata, sin código nuevo)
```
CNBV Microcréditos 2024 → Calibrar umbrales con IMOR real mexicano
ENIF 2024 estadísticas → Contextualizar resultados en artículo académico
```

#### Fase 2: Backtesting con datos mexicanos (1-2 semanas)
```
ENIF 2024 microdatos → Descargar, mapear variables, ejecutar MIHAC
ENSAFI 2023 microdatos → Complementar con dimensiones de salud financiera
→ Comparar distribución de dictámenes MIHAC vs. realidad mexicana
```

#### Fase 3: Entrenamiento ML (requiere procesamiento)
```
ENIGH 2022 + ENIF 2024 → Dataset combinado para entrenar modelo ML
→ Variable objetivo: derivar de variables de pago/mora disponibles
→ Entrenar modelo con contexto mexicano (vs. German Credit Dataset)
```

---

## PARTE III — MEJORAS ESTÉTICAS Y DE UX

### Problema Principal: Interfaz Genérica con Bootstrap 4

**Síntomas visibles:**
- Colores azul Bootstrap genérico sin identidad propia
- Formularios sin jerarquía visual
- Resultado mostrado como tabla de texto plano
- Sin gráficos de explicación
- No funciona bien en móvil
- Sin modo oscuro

---

### 1. Sistema de Diseño Propio

**Stack propuesto:** Tailwind CSS + Alpine.js (sin frameworks pesados)

**Tipografía:**
```css
/* Google Fonts: 2 familias máximo */
font-display: 'Lexend'     /* Títulos — moderna, muy legible */
font-body:    'Inter'      /* Texto — estándar industria fintech */
font-mono:    'JetBrains Mono'  /* Números, código */
```

**Paleta de colores rediseñada:**
```css
/* Primarios — confianza y profesionalismo */
--navy:     #0D1B2A  /* Fondo oscuro, headers */
--blue:     #1B4F8A  /* Acciones primarias */
--teal:     #0E7C7B  /* Acciones secundarias */

/* Estados — feedback visual claro */
--success:  #10B981  /* APROBADO */
--warning:  #F59E0B  /* REVISIÓN MANUAL */
--danger:   #EF4444  /* RECHAZADO */

/* Neutros premium */
--gray-50:  #F9FAFB  /* Fondos de página */
--gray-100: #F3F4F6  /* Fondos de cards */
--gray-200: #E5E7EB  /* Bordes suaves */
--gray-700: #374151  /* Texto secundario */
--gray-900: #111827  /* Texto principal */
```

---

### 2. Dashboard Rediseñado

**Antes:** Página sin sidebar, menú horizontal, tablas básicas.

**Después:** Sidebar fijo + header contextual + cards con métricas + gráficos

**Estructura de pantalla:**

```
┌──────────────────────────────────────────────────────────────┐
│  ┌────────┐  ┌──────────────────────────────────────────────┐│
│  │        │  │  Dashboard                        [Usuario]  ││
│  │  MIHAC │  ├──────────────────────────────────────────────┤│
│  │  v2.0  │  │                                              ││
│  │        │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐    ││
│  ├────────┤  │  │  1,247   │ │  52.3%   │ │   67.8   │    ││
│  │ 📊     │  │  │  Evalúas │ │  Aprob.  │ │  Score   │    ││
│  │ Dash   │◄ │  └──────────┘ └──────────┘ └──────────┘    ││
│  │        │  │                                              ││
│  │ 📋     │  │  ┌─────────────────┐  ┌──────────────────┐  ││
│  │ Nueva  │  │  │ Evaluaciones/día│  │ Distribución     │  ││
│  │ Eval.  │  │  │  [Line Chart]   │  │ dictámenes       │  ││
│  │        │  │  │                 │  │  [Donut Chart]   │  ││
│  │ 🕐     │  │  └─────────────────┘  └──────────────────┘  ││
│  │ Hist.  │  │                                              ││
│  │        │  │  Evaluaciones Recientes                      ││
│  │ 📈     │  │  [Tabla con badges de color por dictamen]    ││
│  │ Monitor│  │                                              ││
│  │        │  └──────────────────────────────────────────────┘│
│  └────────┘                                                   │
└──────────────────────────────────────────────────────────────┘
```

---

### 3. Formulario de Evaluación en Pasos (Multi-step)

**Antes:** Un solo formulario largo con todos los campos juntos.

**Después:** Wizard de 3 pasos con progreso visual.

```
[━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━]
    Paso 1 de 3                    Paso 2 de 3        Paso 3 de 3
  [●] Personal              [ ] Financiero        [ ] Laboral
    Completado               En progreso           Pendiente

┌────────────────────────────────────────┐
│  👤 Datos Personales                   │
│                                        │
│  Edad          [35      ]              │
│  Dependientes  [  2     ]              │
│  Tipo vivienda [▼ Propia]              │
│                                        │
│                [Siguiente →]           │
└────────────────────────────────────────┘
```

**Beneficio:** Reduce la carga cognitiva. El formulario se ve menos intimidante al estar dividido en pasos lógicos.

---

### 4. Página de Resultados con Impacto Visual

**Antes:** Texto plano con el dictamen y una lista de reglas.

**Después:**

```
┌────────────────────────────────────────────┐
│  Gradiente según dictamen:                 │
│  APROBADO → Verde oscuro a verde claro     │
│  RECHAZADO → Rojo oscuro a rojo claro      │
│  REVISIÓN → Naranja oscuro a naranja claro │
│                                            │
│  [ÍCONO SVG GRANDE — Check/X/Warning]      │
│  APROBADO                                  │
│  "Crédito aprobado — Proceder con..."      │
└────────────────────────────────────────────┘

[━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━] 82/100

┌───────────────────┐  ┌────────────────────┐
│ Construcción del  │  │ Perfil del         │
│ Score (Waterfall) │  │ Solicitante (Radar)│
│ [Gráfico plotly]  │  │ [Gráfico plotly]   │
└───────────────────┘  └────────────────────┘

Factores que influyeron:
┌────────────────────────────────────────┐
│ ✅ +20  Historial crediticio bueno     │
│ ✅ +15  Alta estabilidad laboral       │
│ ✅ +10  Vivienda propia                │
│ ✅ +12  Sin deudas con trayectoria     │
│ ❌ -10  Carga familiar alta (3 dep.)   │
└────────────────────────────────────────┘
```

---

### 5. Modo Oscuro Automático

**Por qué es importante en fintech:**
- Muchos analistas trabajan en ambientes de poca luz
- Reduce fatiga visual en sesiones largas
- Tendencia estándar en aplicaciones financieras profesionales

**Implementación simple con Tailwind:**
```html
<html class="dark">
  <body class="bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
    <!-- Todo el resto funciona automáticamente con variantes dark: -->
    <div class="bg-gray-100 dark:bg-gray-800 rounded-lg p-6">
      <h3 class="text-gray-900 dark:text-white">Evaluación</h3>
    </div>
  </body>
</html>
```

**Toggle del usuario:**
```javascript
// Alpine.js — 3 líneas para modo oscuro con preferencia guardada
document.documentElement.classList.toggle('dark',
  localStorage.theme === 'dark' ||
  (!localStorage.theme && window.matchMedia('(prefers-color-scheme: dark)').matches)
)
```

---

### 6. Micro-interacciones y Animaciones

**Objetivo:** Que la interfaz "responda" visualmente a las acciones del usuario.

**Animaciones propuestas:**

```css
/* Score animado al cargar resultados */
@keyframes score-reveal {
  from { opacity: 0; transform: scale(0.5); }
  to   { opacity: 1; transform: scale(1); }
}

.score-number {
  animation: score-reveal 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
}

/* Progress bar animada */
.progress-bar {
  animation: fill 1.2s ease-out;
}

@keyframes fill {
  from { width: 0%; }
  to   { width: var(--score-percentage); }
}

/* Cards con hover elevation */
.card {
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 25px rgba(0,0,0,0.15);
}

/* Botón de evaluar con feedback */
.btn-evaluate:active {
  transform: scale(0.97);
}

/* Loading state */
.btn-evaluate.loading {
  pointer-events: none;
  opacity: 0.7;
}
.btn-evaluate.loading::after {
  content: '';
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid transparent;
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-left: 8px;
}
```

---

### 7. Responsive Mobile-First

**Problema actual:** Formularios no adaptados para pantallas pequeñas.

**Breakpoints con Tailwind:**
```html
<!-- Grid responsive automático -->
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
  <!-- Cards de métricas -->
</div>

<!-- Sidebar colapsable en móvil -->
<aside class="fixed inset-y-0 left-0 w-64
              transform -translate-x-full md:translate-x-0
              transition-transform duration-200 ease-in-out">
  <!-- Sidebar content -->
</aside>

<!-- Botón hamburguesa solo en móvil -->
<button class="md:hidden" @click="sidebarOpen = !sidebarOpen">
  <svg>...</svg>
</button>
```

---

### 8. Referencia Visual: Paleta y Componentes Clave

#### Cards de Resultado

**APROBADO:**
```
Borde izquierdo: 4px solid #10B981 (green)
Fondo: #F0FDF4 (green-50)
Badge: "APROBADO" en pill verde
Ícono: Check circle verde
```

**RECHAZADO:**
```
Borde izquierdo: 4px solid #EF4444 (red)
Fondo: #FEF2F2 (red-50)
Badge: "RECHAZADO" en pill rojo
Ícono: X circle rojo
```

**REVISIÓN MANUAL:**
```
Borde izquierdo: 4px solid #F59E0B (amber)
Fondo: #FFFBEB (yellow-50)
Badge: "REVISIÓN" en pill naranja
Ícono: Warning triangle naranja
```

#### Tabla de Evaluaciones con Badges

```html
<!-- En lugar de texto plano, badges con color -->
{% if row.dictamen == 'APROBADO' %}
  <span class="px-2.5 py-0.5 rounded-full text-xs font-medium
               bg-green-100 text-green-800">
    APROBADO
  </span>
{% elif row.dictamen == 'RECHAZADO' %}
  <span class="px-2.5 py-0.5 rounded-full text-xs font-medium
               bg-red-100 text-red-800">
    RECHAZADO
  </span>
{% else %}
  <span class="px-2.5 py-0.5 rounded-full text-xs font-medium
               bg-yellow-100 text-yellow-800">
    REVISIÓN
  </span>
{% endif %}
```

---

## Roadmap de Implementación Priorizado

### Prioridad ALTA — Impacto inmediato (2-4 semanas)

| # | Mejora | Esfuerzo | Impacto |
|---|--------|----------|---------|
| 1 | Migrar Bootstrap → Tailwind CSS | 3 días | ⭐⭐⭐⭐⭐ |
| 2 | API REST básica (evaluate + history) | 4 días | ⭐⭐⭐⭐⭐ |
| 3 | Página de resultados con gráficos Plotly | 2 días | ⭐⭐⭐⭐⭐ |
| 4 | Badges de color en dictámenes | 1 hora | ⭐⭐⭐⭐ |
| 5 | Validación de MIHAC con ENIF 2024 | 3 días | ⭐⭐⭐⭐ |

### Prioridad MEDIA — Evolución del sistema (1-3 meses)

| # | Mejora | Esfuerzo | Impacto |
|---|--------|----------|---------|
| 6 | Motor híbrido (reglas + ML) | 3 semanas | ⭐⭐⭐⭐⭐ |
| 7 | Formulario multi-step | 2 días | ⭐⭐⭐⭐ |
| 8 | Modo oscuro | 1 día | ⭐⭐⭐ |
| 9 | Migrar SQLite → PostgreSQL | 3 días | ⭐⭐⭐⭐ |
| 10 | Dashboard con Chart.js | 4 días | ⭐⭐⭐⭐ |

### Prioridad BAJA — Excelencia (3-6 meses)

| # | Mejora | Esfuerzo | Impacto |
|---|--------|----------|---------|
| 11 | Calibración automática de pesos | 2 semanas | ⭐⭐⭐⭐⭐ |
| 12 | Drift detection y alertas | 1 semana | ⭐⭐⭐⭐ |
| 13 | Modo batch (CSV input) | 3 días | ⭐⭐⭐ |
| 14 | Micro-animaciones CSS | 1 día | ⭐⭐⭐ |
| 15 | Mobile responsive completo | 3 días | ⭐⭐⭐⭐ |

---

## Quick Wins Inmediatos (Menos de 1 día cada uno)

### Quick Win #1 — Badges de Color (30 minutos)
Reemplazar texto plano "APROBADO" por badges con color en toda la app.

### Quick Win #2 — Fuente Inter (10 minutos)
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>body { font-family: 'Inter', sans-serif; }</style>
```
Resultado instantáneo: La app se ve 40% más profesional.

### Quick Win #3 — Progress Bar en Resultados (1 hora)
Agregar una barra de progreso animada que muestre el score visualmente.

### Quick Win #4 — Waterfall Chart (2 horas)
```python
pip install plotly
# Agregar gráfico de waterfall en la página de resultados
```
Resultado: La explicabilidad del sistema se vuelve visualmente obvia.

### Quick Win #5 — Validación con ENIF 2024 (1 día + escritura)
Descargar ENIF 2024, ejecutar MIHAC sobre los datos, comparar distribución de dictámenes con estadísticas nacionales. Agregar tabla al artículo académico.

---

## Resumen Ejecutivo

| Dimensión | v1.0 Actual | v2.0 Propuesto |
|-----------|-------------|----------------|
| **Motor** | Reglas estáticas | Híbrido (reglas + ML calibrado) |
| **Datos** | German Credit (1994, alemán) | ENIF 2024 + ENSAFI 2023 (mexicano) |
| **API** | No existe | REST + Swagger docs |
| **Interfaz** | Bootstrap genérico | Tailwind + Inter + modo oscuro |
| **Explicación** | Texto plano | Waterfall + Radar (Plotly) |
| **Formulario** | Una página larga | Wizard de 3 pasos |
| **Resultados** | Tabla de texto | Cards con animaciones y gráficos |
| **Mobile** | No responsive | Mobile-first |
| **Monitoreo** | No existe | Drift detection + alertas |
| **Base de datos** | SQLite | PostgreSQL + auditoría |

**El conjunto de estas mejoras transforma MIHAC de un prototipo académico a un producto de software de calidad comercial.**
