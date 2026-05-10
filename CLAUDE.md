# MIHAC — Contexto del Proyecto

## Descripción

MIHAC (Motor de Inferencia Heurística para Aprobación de Créditos) es un
sistema experto basado en reglas heurísticas para evaluación de solicitudes
de microcrédito. Proyecto de tesis de ingeniería en software (UAEH - EST).

**Estado actual:** v1.0 funcional con 254 tests pasando (92% cobertura)
**Objetivo:** Evolucionar a v2.0 de forma incremental sin romper v1.0

---

## Stack

- Python 3.11 + Flask 2.x
- SQLite (mihac.db)
- Bootstrap 4 + Jinja2 templates
- pytest (254 tests, 92% cobertura)
- ReportLab (PDFs)

---

## Estructura de Archivos

```
mihac/
├── app.py                 # Flask app — rutas HTML y configuración
├── engine/
│   ├── engine.py          # InferenceEngine ← núcleo, NO tocar sin tests
│   ├── validator.py       # Validación de las 9 variables de entrada
│   ├── scorer.py          # Cálculo de 4 sub-scores
│   └── explainer.py       # Genera explicación en texto plano
├── knowledge/
│   ├── rules.json         # 15 reglas heurísticas (editable con cuidado)
│   └── weights.json       # Pesos de sub-scores
├── data/
│   ├── mapper.py          # Mapeo de variables externas a formato MIHAC
│   └── models.py          # SQLAlchemy models (SQLite)
├── reports/
│   └── pdf_generator.py   # PDFs con ReportLab
├── templates/             # Jinja2 HTML (Bootstrap 4)
├── static/                # CSS/JS
├── tests/                 # pytest suite
└── demo/
    └── demo_defensa.py    # Demo para defensa de tesis
```

---

## Variables de Entrada (9)

| Variable | Tipo | Valores |
|----------|------|---------|
| edad | int | 18–99 |
| ingreso_mensual | float | > 0 MXN |
| total_deuda_actual | float | >= 0 MXN |
| historial_crediticio | int | 0=Malo, 1=Neutro, 2=Bueno |
| antiguedad_laboral | int | años >= 0 |
| numero_dependientes | int | >= 0 |
| tipo_vivienda | str | 'Propia' / 'Rentada' / 'Prestada' / 'Otro' |
| proposito_credito | str | 'Negocio' / 'Educacion' / 'Personal' / 'Vacaciones' / 'Emergencia' |
| monto_credito | float | 500–50,000 MXN |

## Lógica de Dictamen

- score >= 80 → APROBADO
- score 55–79 → REVISIÓN_MANUAL
- score < 55 → RECHAZADO
- DTI > 60% → RECHAZADO inmediato (veto, ignora score)

---

## Las 15 Reglas (rules.json)

**Directas (11):**
- R001: historial==2 (Bueno) → +20
- R002: historial==0 (Malo) → -25
- R003: antiguedad>=5 → +15
- R004: antiguedad<1 → -10
- R005: vivienda=='Propia' → +10
- R006: proposito=='Negocio' → +8
- R007: proposito=='Educacion' → +6
- R008: proposito=='Vacaciones' → -8
- R009: edad<21 → -12
- R010: dependientes>=4 → -10
- R014: DTI>0.40 → -20

**Compensación (4):**
- R011: historial==1 AND DTI<0.25 AND antiguedad>=3 → +15
- R012: ratio_ingreso_monto>=0.25 AND historial!=0 → +10
- R013: deuda_total==0 AND antiguedad>=2 → +12
- R015: dependientes==0 AND vivienda=='Propia' AND antiguedad>=3 → +8

---

## Convenciones

- Código en inglés, comentarios/docstrings en español
- Formato: Black (PEP 8)
- Tests: pytest — deben pasar ANTES de cualquier commit
- Módulos v2: sufijo `_v2` hasta estar en producción
- Activación v2: variable de entorno MIHAC_V2=true / MIHAC_V2_UI=true
- Commits: feat: / fix: / refactor: / test: / docs:

---

## Reglas de Oro

1. Los 254 tests deben pasar después de cualquier cambio
2. No reescribir lo que funciona — solo extender
3. v1.0 debe seguir funcionando cuando MIHAC_V2=false
4. Explorar archivos/datasets antes de implementar
5. Preguntar si la especificación es ambigua — no asumir
6. Un módulo a la vez por sesión

---

## Paleta de Colores v2

```
Navy:    #0D1B2A   Blue:    #1B4F8A   Teal:    #0E7C7B
Success: #10B981   Warning: #F59E0B   Danger:  #EF4444
```

Fuentes objetivo: Inter (cuerpo) + Lexend (títulos)

---

## Módulos v2 — Estado

- [ ] Módulo A: Mapeo de dataset mexicano (ENIF 2024)
- [ ] Módulo B: Backtesting con datos mexicanos
- [ ] Módulo C: Modelo ML baseline
- [ ] Módulo D: Motor híbrido (Reglas + ML)
- [ ] Módulo E: API REST v2 + Swagger
- [ ] Módulo F: Rediseño visual (Tailwind + Plotly)
- [ ] Módulo G: Calibración con datos CNBV

---

## Documentos de Referencia

- `MIHAC_Prompt_v2_Maestro.md` — Plan completo de evolución
- `MIHAC_v2_Mejoras_Datasets_Estetica.md` — Especificaciones detalladas
