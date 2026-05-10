# MIHAC v2.0 — API REST v2

**Base URL:** `http://localhost:5000`
**Versión motor:** 2.0.0
**Spec OpenAPI:** [`GET /api/v2/openapi.json`](http://localhost:5000/api/v2/openapi.json)
**Swagger UI interactivo:** [`GET /api/v2/docs`](http://localhost:5000/api/v2/docs)

## Cómo levantar el servidor

```bash
# Desde la carpeta mihac/
python run.py
# → http://localhost:5000
```

Para activar la calibración México por defecto en todo el proceso:

```bash
# PowerShell (Windows)
$env:MIHAC_THRESHOLDS_FILE = "thresholds_mx.json"
python run.py

# Bash
MIHAC_THRESHOLDS_FILE=thresholds_mx.json python run.py
```

Alternativamente, puedes pedir el perfil MX por request usando `?perfil=mx` o `"perfil": "mx"` en el body — sin reiniciar el servidor.

---

## Convenciones generales

- Todas las requests POST deben enviar `Content-Type: application/json`.
- Códigos de respuesta:
  - **200** OK
  - **400** Validación de payload fallida (`{"errores_validacion": [...]}`)
  - **422** Reglas de negocio (lote excede 100, etc.)
  - **500** Error interno (raro — todos los errores del motor se capturan)
- Convención del motor:
  - `dictamen ∈ {"APROBADO", "REVISION_MANUAL", "RECHAZADO"}`
  - `score_final ∈ [0, 100]`
  - `dti_clasificacion ∈ {"BAJO", "MODERADO", "ALTO", "CRITICO"}`
  - DTI CRITICO → veto automático que fuerza RECHAZADO

## Las 9 variables de entrada

| Campo | Tipo | Rango / Valores |
|---|---|---|
| `edad` | int | 18–99 |
| `ingreso_mensual` | float | > 0 (MXN) |
| `total_deuda_actual` | float | ≥ 0 (MXN) |
| `historial_crediticio` | int | 0=Malo, 1=Neutro, 2=Bueno |
| `antiguedad_laboral` | int | 0–40 (años) |
| `numero_dependientes` | int | 0–10 |
| `tipo_vivienda` | str | `Propia` / `Familiar` / `Rentada` |
| `proposito_credito` | str | `Negocio` / `Educacion` / `Consumo` / `Emergencia` / `Vacaciones` |
| `monto_credito` | float | 500–50,000 (MXN) |

Campo opcional adicional:

| Campo | Tipo | Default | Efecto |
|---|---|---|---|
| `perfil` | str | `v1` | `v1` = umbrales hardcoded ; `mx` = activa `thresholds_mx.json` |

---

## 1. POST `/api/v2/evaluate`

Evalúa una solicitud crediticia individual.

### Request

```bash
curl -X POST http://localhost:5000/api/v2/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "edad": 35,
    "ingreso_mensual": 25000.0,
    "total_deuda_actual": 4000.0,
    "historial_crediticio": 2,
    "antiguedad_laboral": 7,
    "numero_dependientes": 1,
    "tipo_vivienda": "Propia",
    "proposito_credito": "Negocio",
    "monto_credito": 15000.0
  }'
```

### Response 200

```json
{
  "request_id": "eval_a1b2c3d4e5f6",
  "timestamp": "2026-05-10T13:45:01Z",
  "perfil_calibracion": "v1",
  "umbrales_activos": "(hardcoded v1.0)",
  "evaluacion_id": 42,
  "tiempo_evaluacion_ms": 0.421,
  "version_motor": "2.0.0",
  "dictamen": "APROBADO",
  "score_final": 95,
  "dti_ratio": 0.16,
  "dti_clasificacion": "BAJO",
  "umbral_aplicado": 80,
  "sub_scores": {
    "solvencia": 28,
    "estabilidad": 26,
    "historial_score": 20,
    "perfil": 10
  },
  "reglas_activadas": [
    {"id": "R001", "impacto": 20, "descripcion": "...", "tipo": "directa"},
    {"id": "R003", "impacto": 15, "descripcion": "...", "tipo": "directa"},
    "..."
  ],
  "compensaciones": [...],
  "reporte_explicacion": "El solicitante presenta...",
  "errores_validacion": []
}
```

### Activar calibración MX por request

```bash
# Vía query string
curl -X POST "http://localhost:5000/api/v2/evaluate?perfil=mx" \
  -H "Content-Type: application/json" \
  -d '{ ... }'

# Vía campo en el body
curl -X POST http://localhost:5000/api/v2/evaluate \
  -H "Content-Type: application/json" \
  -d '{ "edad": 35, ..., "perfil": "mx" }'
```

### Errores 400

```bash
curl -X POST http://localhost:5000/api/v2/evaluate \
  -H "Content-Type: application/json" \
  -d '{"edad": 35, "tipo_vivienda": "Cueva"}'
```

```json
{
  "errores_validacion": [
    "campo faltante: ingreso_mensual",
    "campo faltante: total_deuda_actual",
    "...",
    "tipo_vivienda inválido — usar ['Familiar', 'Propia', 'Rentada']"
  ]
}
```

---

## 2. POST `/api/v2/evaluate/batch`

Evalúa hasta **100 solicitudes** en un solo request. Items inválidos se marcan individualmente sin abortar el lote.

### Request

```bash
curl -X POST http://localhost:5000/api/v2/evaluate/batch \
  -H "Content-Type: application/json" \
  -d '{
    "perfil": "mx",
    "solicitudes": [
      { "edad": 35, "ingreso_mensual": 25000.0, ... },
      { "edad": 28, "ingreso_mensual":  8000.0, ... },
      { "edad": 19, "ingreso_mensual":  5000.0, ... }
    ]
  }'
```

### Response 200

```json
{
  "perfil_calibracion": "mx",
  "n_total": 3,
  "distribucion_dictamenes": {
    "APROBADO": 2,
    "REVISION_MANUAL": 1,
    "RECHAZADO": 0
  },
  "resultados": [
    { "indice": 0, "dictamen": "APROBADO", "score_final": 95, ... },
    { "indice": 1, "dictamen": "APROBADO", "score_final": 78, ... },
    { "indice": 2, "dictamen": "REVISION_MANUAL", "score_final": 62, ... }
  ]
}
```

### Error 422 — lote excede 100

```bash
curl -X POST http://localhost:5000/api/v2/evaluate/batch \
  -H "Content-Type: application/json" \
  -d "$(python -c 'import json; print(json.dumps({"solicitudes": [{}]*101}))')"
```

```json
{ "error": "Tamaño de lote excede 100: recibido 101" }
```

---

## 3. GET `/api/v2/history`

Lista evaluaciones previas con paginación y filtro por dictamen.

### Request

```bash
# Página 1, 20 por página (defaults)
curl http://localhost:5000/api/v2/history

# Página 2, 50 por página
curl "http://localhost:5000/api/v2/history?page=2&per_page=50"

# Solo APROBADO
curl "http://localhost:5000/api/v2/history?dictamen=APROBADO"
```

### Response 200

```json
{
  "page": 1,
  "per_page": 20,
  "total": 87,
  "n_paginas": 5,
  "items": [
    {
      "id": 87,
      "timestamp": "2026-05-10T13:45:01.234567",
      "dictamen": "APROBADO",
      "score_final": 95,
      "dti_ratio": 0.16,
      "dti_clasificacion": "BAJO",
      "monto_credito": 15000.0,
      "proposito_credito": "Negocio"
    },
    "..."
  ]
}
```

---

## 4. GET `/api/v2/monitoring/stats`

Agregados de las evaluaciones de los últimos N días.

### Request

```bash
# Default: últimos 30 días
curl http://localhost:5000/api/v2/monitoring/stats

# Últimos 7 días
curl "http://localhost:5000/api/v2/monitoring/stats?days=7"
```

### Response 200

```json
{
  "ventana_dias": 30,
  "n_evaluaciones": 87,
  "tasa_aprobacion": 47.13,
  "tasa_rechazo": 35.63,
  "tasa_revision": 17.24,
  "score_promedio": 67.42,
  "dti_promedio": 0.2854,
  "distribucion": {
    "APROBADO": 41,
    "REVISION_MANUAL": 15,
    "RECHAZADO": 31
  }
}
```

---

## 5. GET `/api/v2/rules`

Devuelve las 15 reglas heurísticas activas y los umbrales del perfil seleccionado.

### Request

```bash
# Perfil v1 (default)
curl http://localhost:5000/api/v2/rules

# Perfil MX (calibración México)
curl "http://localhost:5000/api/v2/rules?perfil=mx"
```

### Response 200

```json
{
  "perfil_calibracion": "mx",
  "thresholds_file": "thresholds_mx.json",
  "thresholds": {
    "_meta": { ... },
    "dictamen": {
      "APROBADO": { "score_minimo": 70, ... },
      "REVISION_MANUAL": { "score_minimo": 55, "score_maximo": 69 },
      "RECHAZADO": { "score_maximo": 54 }
    },
    "dti": {
      "critico": 0.50,
      "alto": 0.40,
      "moderado": 0.30,
      "bajo": 0.20
    },
    "monto_credito_modificador": { "tramos": [...] }
  },
  "rules": {
    "_meta": { "total_reglas": 15 },
    "reglas": [
      { "id": "R001", "descripcion": "...", "impacto_puntos": 20, ... },
      "..."
    ]
  }
}
```

---

## 6. GET `/api/v2/openapi.json`

Devuelve la especificación OpenAPI 3.0 completa del API.

```bash
curl http://localhost:5000/api/v2/openapi.json | jq .info
```

```json
{
  "title": "MIHAC API v2",
  "description": "Motor de Inferencia Heurística para Aprobación...",
  "version": "2.0.0",
  "contact": { "name": "Proyecto MIHAC — Tesis UAEH-EST" }
}
```

## 7. GET `/api/v2/docs`

Swagger UI interactivo (HTML, sin dependencias en el servidor — usa CDN). Permite probar todos los endpoints desde el navegador.

```bash
# Abrir en navegador
xdg-open  http://localhost:5000/api/v2/docs    # Linux
open      http://localhost:5000/api/v2/docs    # macOS
start     http://localhost:5000/api/v2/docs    # Windows PowerShell
```

---

## Diferencia entre `perfil=v1` y `perfil=mx`

| Aspecto | `v1` (default) | `mx` (calibración México) |
|---|---|---|
| Score umbral APROBADO | ≥ 80 | ≥ 70 |
| Score umbral RECHAZADO | < 60 | < 55 |
| Banda REVISION_MANUAL | [60, 79] | [55, 69] |
| DTI CRITICO (veto) | > 0.60 | > 0.65 |
| Ajuste tramo $5K–$15K | +0 | +5 |
| Ajuste tramo $15K–$30K | +5 | +10 |
| Ajuste tramo $30K–$50K | +5 | +15 |

Sobre el dataset ENIF 2024 (5,248 personas observables), el perfil MX:
- Aumenta APROBADO de 2,242 → 2,401 (+159)
- Reduce FN de 1,822 → 1,663 (−159)
- Mantiene Precision = 1.000 (cero FP introducidos)

Ver detalle en `reports/calibration_mx.md`.

---

## Tests

```bash
cd mihac
pytest tests/test_api_v2.py -v
# → 18/18 passed
```

Cobertura de los 7 endpoints + casos de borde (validación, lote excede límite, item inválido en lote, perfil v1 vs mx, filtro por dictamen, etc.).
