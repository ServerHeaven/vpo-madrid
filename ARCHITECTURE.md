# ARCHITECTURE.md — Agregador de alquiler protegido · Comunidad de Madrid

> **Estado:** borrador v0.1 para validación · **Fecha:** 2026-11-27
> **Alcance:** solo diseño. Aquí no hay código de la aplicación. Los fragmentos YAML/JSON/regex son contratos y esqueletos de diseño que se implementan en las fases 1 a 5.

---

## 0. Principios de diseño (no negociables)

1. **Coste 0 € y 100 % GitHub.** Repo público + GitHub Actions + GitHub Pages. Ni servidores, ni BBDD externas, ni APIs de pago.
2. **Git es la base de datos.** Todo dato es un JSON versionado. El historial de Git hace de auditoría: quién cambió qué, cuándo y por qué.
3. **Un `null` vale más que un dato erróneo.** El extractor prioriza la **precisión** sobre la cobertura. Si hay duda (ningún valor, varios valores que se contradicen o un valor fuera de rango), el campo queda en `null` y se abre una revisión manual.
4. **Lo manual nunca se pisa.** Las correcciones humanas viven en `data/overrides.json`, un archivo que el scraper **solo lee** y nunca escribe.
5. **Aislamiento de fallos.** Si cae una fuente (cambio de HTML, timeout o 403), las demás siguen y se conserva el último dato bueno de la fuente caída, marcado como `stale`.
6. **Determinismo y reproducibilidad.** La misma entrada (bytes del HTML/PDF + versión del extractor) produce siempre la misma salida. Cada cambio de reglas de extracción se valida con *golden tests*.
7. **Extracción desacoplada.** El pipeline de extracción depende de una interfaz (`Extractor`) y no de una implementación. Un futuro `LLMExtractor` se registra sin tocar nada más.
8. **Cero datos personales.** Sin cuentas, cookies, analítica, formularios que envíen datos ni parámetros de URL con datos del usuario. La calculadora corre y se olvida en el navegador.
9. **Información orientativa.** Cada ficha remite a la fuente oficial. La web no sustituye a las bases.

---

## 1. Stack recomendado

| Capa | Elección | Motivo |
|---|---|---|
| **Sitio estático** | **Astro 5** (`output: 'static'`) | Genera HTML puro por defecto y solo envía JS a las "islas" interactivas (buscador y calculadora). Crea una página por promoción en build (`getStaticPaths`), con buen SEO, y lee JSON locales sin capa de API. Es más ligero que el `output: export` de Next.js, que en Pages da problemas con `basePath`, imágenes y rutas dinámicas. |
| Islas interactivas | **Preact** (`@astrojs/preact`) | API de React en ~4 KB. Basta para filtros y formulario. |
| Estilos | **Tailwind CSS 4** (plugin Vite) | Sin runtime y con purgado automático. |
| Validación de datos en build | **Ajv** (JSON Schema 2020-12) | Se usa el mismo schema que en Python, así que hay **una sola fuente de verdad**. |
| Tests web | **Vitest** | Tests de la lógica pura de elegibilidad y filtros. |
| Scraper | **Python 3.12** + **httpx** + **selectolax** (o BeautifulSoup + lxml) | HTTP rápido con peticiones condicionales (ETag). selectolax es ~10× más rápido que bs4. bs4 queda como fallback por legibilidad. |
| Navegador headless | **Playwright (Chromium)**, *solo* en fuentes que lo necesiten | Las webs con contenido renderizado por JS (portales de operadoras) lo necesitan. Por defecto se usa httpx y Playwright es opcional por fuente. |
| PDF | **PyMuPDF** (texto y layout, rápido) + **pdfplumber** (tablas) | PyMuPDF para el texto y bloques con coordenadas. pdfplumber para las tablas de rentas por tipología. |
| Modelos y validación Python | **Pydantic v2** + **jsonschema** | Modelos tipados para la lógica y validación final contra el JSON Schema compartido. |
| Tests Python | **pytest** + *golden files* | Cada PDF/HTML de fixture tiene su JSON esperado. |
| Gestión de deps | **uv** (o pip + `requirements.lock`) | Instalación rápida y cacheable en Actions. |
| Issues | **`gh` CLI** (preinstalado en runners) con `GITHUB_TOKEN` | Sin librerías extra. |
| CI/CD | GitHub Actions: `scrape.yml`, `deploy.yml`, `ci.yml` | Ver §4. |
| Hosting | GitHub Pages (despliegue por artifact, sin rama `gh-pages`) | `actions/upload-pages-artifact` + `actions/deploy-pages`. |

**Requisitos de plataforma:**
- El repo debe ser **público**. Así Actions tiene minutos ilimitados y Pages es gratis en cuentas Free.
- En `astro.config.mjs` hay que fijar `site` y `base: '/<nombre-repo>/'` mientras no haya dominio propio. Todos los enlaces internos deben construirse con `import.meta.env.BASE_URL`.

---

## 2. Estructura del repositorio

```
/
├── ARCHITECTURE.md                  ← este documento
├── README.md                        ← qué es, cómo contribuir correcciones
├── CLAUDE.md                        ← convenciones para Claude Code (Fase 1)
├── LICENSE
│
├── data/                            ← ÚNICA fuente de datos (versionada)
│   ├── promociones.json             ← GENERADO: resultado final fusionado (scraped + overrides)
│   ├── state.json                   ← GENERADO: hashes, ETags, última comprobación, salud de fuentes
│   ├── overrides.json               ← MANUAL: correcciones humanas (el scraper solo lo lee)
│   ├── iprem.json                   ← MANUAL: tabla IPREM por año
│   ├── programas.json               ← MANUAL: reglas por defecto por régimen/programa, con vigencias
│   ├── municipios.json              ← MANUAL (una vez): 179 municipios CAM con código INE
│   ├── fuentes.json                 ← MANUAL: catálogo de fuentes (URL, método, activa, rate limit)
│   ├── sources/                     ← GENERADO: salida cruda por fuente (aislamiento de fallos)
│   │   ├── emvs-madrid.json
│   │   ├── plan-vive-cam.json
│   │   └── …
│   └── schema/                      ← JSON Schemas (contratos compartidos Python ↔ Astro)
│       ├── promociones.schema.json
│       ├── promocion.schema.json    ← $defs reutilizables (una promoción)
│       ├── overrides.schema.json
│       ├── state.schema.json
│       ├── iprem.schema.json
│       ├── programas.schema.json
│       └── fuentes.schema.json
│
├── scraper/                         ← paquete Python
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── src/vpo/
│   │   ├── __main__.py              ← CLI: `python -m vpo run|merge|validate|review|reparse`
│   │   ├── core/
│   │   │   ├── models.py            ← Pydantic: Promocion, Tipologia, Requisitos, FieldResult…
│   │   │   ├── http.py              ← cliente httpx: UA, rate limit, reintentos, ETag/If-Modified-Since
│   │   │   ├── browser.py           ← wrapper Playwright (lazy, solo si la fuente lo pide)
│   │   │   ├── hashing.py           ← sha256 de bytes + sha256 de texto normalizado
│   │   │   ├── state.py             ← lectura/escritura atómica de state.json
│   │   │   ├── ids.py               ← generación de IDs estables (slug)
│   │   │   ├── normalize.py         ← números ES ("1.234,56"), fechas, municipios→INE
│   │   │   └── merge.py             ← sources/*.json + overrides.json → promociones.json
│   │   ├── sources/                 ← un adaptador por fuente (HTML → lista de promociones + PDFs)
│   │   │   ├── base.py              ← interfaz SourceAdapter
│   │   │   ├── registry.py
│   │   │   ├── emvs_madrid.py
│   │   │   ├── plan_vive_cam.py
│   │   │   ├── avalon_convive.py
│   │   │   ├── sogeviso.py
│   │   │   ├── culmia.py
│   │   │   └── emv_municipales/     ← EMV/EMSV de Alcobendas, Getafe, Rivas, Fuenlabrada…
│   │   ├── extraction/              ← DESACOPLADO: documento → campos con confianza
│   │   │   ├── base.py              ← interfaz Extractor, Document, FieldResult, ExtractionResult
│   │   │   ├── pipeline.py          ← orquesta extractores, resuelve conflictos, aplica umbrales
│   │   │   ├── documents/
│   │   │   │   ├── pdf.py           ← PyMuPDF/pdfplumber → Document (texto por página + tablas)
│   │   │   │   └── html.py          ← HTML → Document
│   │   │   ├── preprocess.py        ← limpieza de texto, deshifenado, segmentación por secciones
│   │   │   ├── rules/               ← extractores deterministas (uno por familia de campos)
│   │   │   │   ├── ingresos_iprem.py
│   │   │   │   ├── empadronamiento.py
│   │   │   │   ├── rentas.py
│   │   │   │   ├── fechas.py
│   │   │   │   ├── edad.py
│   │   │   │   ├── tipologias.py
│   │   │   │   └── anejos.py        ← garaje / trastero
│   │   │   ├── patterns.py          ← catálogo de regex con ID (REG-IPREM-01…)
│   │   │   ├── validators.py        ← rangos plausibles, coherencia entre campos
│   │   │   └── llm/                 ← VACÍO salvo README: punto de enchufe futuro
│   │   └── review/
│   │       ├── report.py            ← genera data/review-report.json (efímero, no se commitea)
│   │       └── issues.py            ← sincroniza GitHub Issues vía `gh`
│   └── tests/
│       ├── fixtures/{html,pdf}/     ← copias de documentos reales (ver §7.4 sobre licencias)
│       ├── golden/                  ← salida esperada por fixture
│       ├── test_rules_*.py
│       ├── test_merge.py
│       └── test_schema.py
│
├── web/                             ← sitio Astro
│   ├── package.json
│   ├── astro.config.mjs
│   ├── public/
│   └── src/
│       ├── lib/
│       │   ├── data.ts              ← carga ../data/*.json, valida con Ajv, falla el build si no cuadra
│       │   ├── types.ts             ← tipos generados desde JSON Schema (json-schema-to-typescript)
│       │   ├── eligibility.ts       ← motor de elegibilidad PURO (sin DOM), testeado
│       │   ├── filters.ts           ← lógica de filtros pura
│       │   └── format.ts            ← € y fechas en es-ES
│       ├── islands/
│       │   ├── Buscador.tsx         ← filtros cliente
│       │   └── Calculadora.tsx      ← formulario + resultados
│       ├── components/              ← PromoCard, Trazabilidad, BadgeEstado, AvisoLegal…
│       ├── layouts/Base.astro
│       └── pages/
│           ├── index.astro          ← buscador
│           ├── promociones/[id].astro
│           ├── calculadora.astro
│           ├── metodologia.astro    ← cómo se obtienen los datos, límites, cómo corregir
│           ├── fuentes.astro        ← estado de cada fuente (desde state.json)
│           └── aviso-legal.astro
│
└── .github/
    ├── workflows/
    │   ├── scrape.yml
    │   ├── deploy.yml
    │   └── ci.yml
    ├── ISSUE_TEMPLATE/
    │   ├── correccion-dato.yml      ← para que terceros reporten errores
    │   └── nueva-fuente.yml
    └── labels.yml                   ← definición de etiquetas (needs-review, scraper-broken…)
```

**Archivos generados frente a manuales:** el workflow `scrape.yml` solo puede escribir en `data/promociones.json`, `data/state.json` y `data/sources/*.json`. `ci.yml` rechaza cualquier commit del bot que toque otros archivos de `data/`.

---

## 3. Contratos de datos

### 3.1 Convenciones comunes

- **Todas las claves son obligatorias** (`required` completo) y los desconocidos son `null`. Así "no lo sabemos" (`null`) queda separado de "el scraper ni lo intentó" (clave ausente, que sería un error de schema).
- Todos los objetos llevan `additionalProperties: false`.
- Importes en **euros, número decimal**, renta **mensual** sin IVA ni gastos salvo que se indique otra cosa.
- Fechas en ISO 8601 (`YYYY-MM-DD`) y marcas de tiempo en UTC (`date-time`).
- Municipios por **código INE** de 5 dígitos (`28xxx`), más el nombre para mostrar.
- Los multiplicadores IPREM se guardan como número (`5.5`, no `"5,5"`).
- **ID estable de promoción:** `{operador}-{municipio-slug}-{nombre-slug}`, p. ej. `emvs-madrid-madrid-vallecas-ensanche-34`. Lo genera `ids.py` una sola vez y queda **congelado** en `state.json` (`promo_ids` por URL canónica), de modo que un cambio de nombre en origen no rompe enlaces.

### 3.2 `data/schema/promociones.schema.json` (estricto)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.invalid/schema/promociones.schema.json",
  "title": "Promociones de alquiler protegido – Comunidad de Madrid",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "generado_en", "promociones"],
  "properties": {
    "schema_version": { "const": 1 },
    "generado_en": { "type": "string", "format": "date-time" },
    "promociones": {
      "type": "array",
      "items": { "$ref": "#/$defs/promocion" }
    }
  },

  "$defs": {
    "nullableNumber":  { "type": ["number", "null"] },
    "nullableInt":     { "type": ["integer", "null"] },
    "nullableString":  { "type": ["string", "null"] },
    "nullableDate":    { "type": ["string", "null"], "format": "date" },
    "nullableBool":    { "type": ["boolean", "null"] },
    "eur":             { "type": ["number", "null"], "minimum": 0, "maximum": 10000 },
    "ivecesIprem":     { "type": ["number", "null"], "minimum": 0, "maximum": 15 },

    "promocion": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "id", "nombre", "operador", "fuente_id", "regimen", "programa",
        "modalidad", "estado", "ubicacion", "viviendas_total", "tipologias",
        "requisitos", "fechas", "enlaces", "meta"
      ],
      "properties": {
        "id":        { "type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$", "maxLength": 120 },
        "nombre":    { "type": "string", "minLength": 2, "maxLength": 200 },
        "operador": {
          "type": "object", "additionalProperties": false,
          "required": ["id", "nombre", "tipo"],
          "properties": {
            "id":     { "type": "string", "pattern": "^[a-z0-9-]+$" },
            "nombre": { "type": "string" },
            "tipo":   { "enum": ["publico_autonomico", "publico_municipal", "privado_concesionario", "cooperativa", "otro"] }
          }
        },
        "fuente_id": { "type": "string", "pattern": "^[a-z0-9-]+$" },

        "regimen": {
          "description": "Calificación legal de la vivienda",
          "enum": ["VPPB", "VPPL", "VPPA", "VPO", "ASEQUIBLE_NO_CALIFICADA", "DESCONOCIDO"]
        },
        "programa": {
          "description": "Programa o canal de adjudicación",
          "enum": ["PLAN_VIVE", "EMVS_MADRID", "EMV_MUNICIPAL", "AVS_CAM", "COOPERATIVA", "PROMOTOR_PRIVADO", "OTRO", null]
        },
        "modalidad": { "enum": ["alquiler", "alquiler_opcion_compra"] },
        "estado": {
          "enum": [
            "proxima",
            "inscripcion_abierta",
            "inscripcion_cerrada",
            "sorteo_adjudicacion",
            "lista_espera_abierta",
            "finalizada",
            "desconocido"
          ]
        },

        "ubicacion": {
          "type": "object", "additionalProperties": false,
          "required": ["municipio_ine", "municipio", "distrito", "direccion", "lat", "lon"],
          "properties": {
            "municipio_ine": { "type": "string", "pattern": "^28[0-9]{3}$" },
            "municipio":     { "type": "string" },
            "distrito":      { "$ref": "#/$defs/nullableString" },
            "direccion":     { "$ref": "#/$defs/nullableString" },
            "lat":           { "type": ["number", "null"], "minimum": 39.8, "maximum": 41.2 },
            "lon":           { "type": ["number", "null"], "minimum": -4.6, "maximum": -3.0 }
          }
        },

        "viviendas_total": { "type": ["integer", "null"], "minimum": 1, "maximum": 5000 },

        "tipologias": {
          "type": "array",
          "items": { "$ref": "#/$defs/tipologia" }
        },

        "requisitos": { "$ref": "#/$defs/requisitos" },

        "fechas": {
          "type": "object", "additionalProperties": false,
          "required": ["inscripcion_inicio", "inscripcion_fin", "sorteo", "entrega_prevista"],
          "properties": {
            "inscripcion_inicio": { "$ref": "#/$defs/nullableDate" },
            "inscripcion_fin":    { "$ref": "#/$defs/nullableDate" },
            "sorteo":             { "$ref": "#/$defs/nullableDate" },
            "entrega_prevista": {
              "description": "Texto libre normalizado: '2027', '2027-T2', '2027-06'",
              "type": ["string", "null"], "pattern": "^[0-9]{4}(-(T[1-4]|0[1-9]|1[0-2]))?$"
            }
          }
        },

        "enlaces": {
          "type": "object", "additionalProperties": false,
          "required": ["oficial", "solicitud", "bases"],
          "properties": {
            "oficial":   { "type": "string", "format": "uri" },
            "solicitud": { "type": ["string", "null"], "format": "uri" },
            "bases": {
              "type": "array",
              "items": {
                "type": "object", "additionalProperties": false,
                "required": ["url", "titulo", "sha256", "detectado_en", "es_principal"],
                "properties": {
                  "url":          { "type": "string", "format": "uri" },
                  "titulo":       { "type": "string" },
                  "sha256":       { "type": "string", "pattern": "^[a-f0-9]{64}$" },
                  "detectado_en": { "type": "string", "format": "date" },
                  "es_principal": { "type": "boolean" }
                }
              }
            }
          }
        },

        "meta": { "$ref": "#/$defs/meta" }
      }
    },

    "tipologia": {
      "type": "object", "additionalProperties": false,
      "required": ["dormitorios", "superficie_util_m2", "renta_mensual_eur", "renta_mensual_max_eur",
                   "num_viviendas", "garaje", "trastero", "adaptada_pmr"],
      "properties": {
        "dormitorios":           { "type": ["integer", "null"], "minimum": 0, "maximum": 6 },
        "superficie_util_m2":    { "type": ["number", "null"], "minimum": 15, "maximum": 200 },
        "renta_mensual_eur":     { "$ref": "#/$defs/eur", "description": "Renta (o renta mínima si hay horquilla)" },
        "renta_mensual_max_eur": { "$ref": "#/$defs/eur", "description": "Solo si la bases dan horquilla" },
        "num_viviendas":         { "type": ["integer", "null"], "minimum": 1 },
        "garaje":   { "$ref": "#/$defs/anejo" },
        "trastero": { "$ref": "#/$defs/anejo" },
        "adaptada_pmr": { "$ref": "#/$defs/nullableBool" }
      }
    },

    "anejo": {
      "type": "object", "additionalProperties": false,
      "required": ["disponibilidad", "precio_mensual_eur"],
      "properties": {
        "disponibilidad":     { "enum": ["incluido", "opcional", "no", "desconocido"] },
        "precio_mensual_eur": { "$ref": "#/$defs/eur" }
      }
    },

    "requisitos": {
      "type": "object", "additionalProperties": false,
      "required": [
        "ingresos_min_iprem", "ingresos_max_iprem", "ingresos_por_miembros",
        "iprem_pagas", "iprem_ejercicio", "tasa_esfuerzo_max",
        "empadronamiento", "edad", "no_titular_vivienda", "no_exigidos", "otros"
      ],
      "properties": {
        "ingresos_min_iprem": { "$ref": "#/$defs/ivecesIprem" },
        "ingresos_max_iprem": { "$ref": "#/$defs/ivecesIprem" },
        "ingresos_por_miembros": {
          "description": "Tabla escalonada si las bases fijan límites por tamaño de unidad. Si existe, prevalece sobre min/max planos.",
          "type": ["array", "null"],
          "items": {
            "type": "object", "additionalProperties": false,
            "required": ["miembros_desde", "miembros_hasta", "min_iprem", "max_iprem"],
            "properties": {
              "miembros_desde": { "type": "integer", "minimum": 1 },
              "miembros_hasta": { "type": ["integer", "null"], "minimum": 1 },
              "min_iprem":      { "$ref": "#/$defs/ivecesIprem" },
              "max_iprem":      { "$ref": "#/$defs/ivecesIprem" }
            }
          }
        },
        "iprem_pagas":      { "enum": [12, 14, null] },
        "iprem_ejercicio":  { "type": ["integer", "null"], "minimum": 2015, "maximum": 2100 },
        "tasa_esfuerzo_max":{ "type": ["number", "null"], "exclusiveMinimum": 0, "maximum": 1 },
        "empadronamiento": {
          "type": ["object", "null"], "additionalProperties": false,
          "required": ["ambito", "municipio_ine", "anios_min", "ininterrumpido", "alternativa_trabajo"],
          "properties": {
            "ambito":              { "enum": ["municipio", "comunidad"] },
            "municipio_ine":       { "type": ["string", "null"], "pattern": "^28[0-9]{3}$" },
            "anios_min":           { "type": ["number", "null"], "minimum": 0, "maximum": 20 },
            "ininterrumpido":      { "$ref": "#/$defs/nullableBool" },
            "alternativa_trabajo": { "$ref": "#/$defs/nullableBool",
                                     "description": "true si trabajar en el municipio/CAM sustituye al empadronamiento" }
          }
        },
        "edad": {
          "type": ["object", "null"], "additionalProperties": false,
          "required": ["min", "max", "tipo"],
          "properties": {
            "min":  { "type": ["integer", "null"], "minimum": 16, "maximum": 99 },
            "max":  { "type": ["integer", "null"], "minimum": 16, "maximum": 120 },
            "tipo": { "enum": ["requisito", "cupo"],
                      "description": "requisito = excluyente; cupo = reserva de un % para ese tramo" }
          }
        },
        "no_titular_vivienda": { "$ref": "#/$defs/nullableBool" },
        "no_exigidos": {
          "description": "Requisitos que consta que no se exigen (ADR-001 §1)",
          "type": "array", "uniqueItems": true,
          "items": { "enum": ["ingresos_min_iprem", "ingresos_max_iprem", "tasa_esfuerzo_max",
                              "empadronamiento", "edad", "no_titular_vivienda"] }
        },
        "otros": { "type": "array", "items": { "type": "string", "maxLength": 300 } }
      }
    },

    "meta": {
      "type": "object", "additionalProperties": false,
      "required": ["primera_deteccion", "ultima_modificacion", "activa_en_fuente",
                   "campos_pendientes", "campos_override", "procedencia", "extractor_version"],
      "properties": {
        "primera_deteccion":   { "type": "string", "format": "date" },
        "ultima_modificacion": { "type": "string", "format": "date",
                                 "description": "Último día en que cambió algún dato (no la comprobación)" },
        "activa_en_fuente":    { "type": "boolean",
                                 "description": "false si la promoción desaparece del listado de origen" },
        "campos_pendientes":   { "type": "array", "items": { "type": "string", "pattern": "^/" },
                                 "description": "JSON Pointers de campos clave en null que requieren revisión" },
        "campos_override":     { "type": "array", "items": { "type": "string", "pattern": "^/" } },
        "procedencia": {
          "description": "JSON Pointer → cómo se obtuvo el valor",
          "type": "object",
          "additionalProperties": {
            "type": "object", "additionalProperties": false,
            "required": ["metodo", "confianza", "documento", "pagina", "evidencia", "regla"],
            "properties": {
              "metodo":    { "enum": ["html", "pdf_texto", "pdf_tabla", "override", "default_programa", "llm"] },
              "confianza": { "type": "number", "minimum": 0, "maximum": 1 },
              "documento": { "type": ["string", "null"], "format": "uri" },
              "pagina":    { "type": ["integer", "null"], "minimum": 1 },
              "evidencia": { "type": ["string", "null"], "maxLength": 400 },
              "regla":     { "type": ["string", "null"], "description": "ID de patrón, p. ej. REG-IPREM-02" }
            }
          }
        },
        "extractor_version": { "type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$" }
      }
    }
  }
}
```

**Campos clave**, que generan revisión si quedan en `null` y la fuente tiene un PDF de bases: `estado`, `ubicacion.municipio_ine`, `tipologias[*].renta_mensual_eur`, `requisitos.ingresos_max_iprem` (o `ingresos_por_miembros`), `requisitos.empadronamiento` y `fechas.inscripcion_fin` cuando `estado = inscripcion_abierta`. La lista vive en `scraper/src/vpo/review/report.py` como constante, para cambiarla sin tocar el schema.

> **¿Por qué la "última comprobación" no está en `promociones.json`?** Cambia todos los días y llenaría de ruido los diffs de datos reales. Vive en `state.json` y el build de Astro la cruza por `fuente_id` y URL. Así un diff en `promociones.json` significa siempre un cambio real de datos.

### 3.3 `data/overrides.json`

```json
{
  "$schema": "./schema/overrides.schema.json",
  "schema_version": 1,
  "overrides": {
    "emvs-madrid-madrid-vallecas-ensanche-34": {
      "campos": {
        "/requisitos/ingresos_max_iprem": {
          "valor": 5.5,
          "motivo": "Bases p.4, tabla 2; el regex captó 7,5 de un párrafo de normativa general",
          "autor": "github-handle",
          "fecha": "2026-11-27",
          "fuente_sha256": "9f2c…(sha256 del PDF revisado)"
        },
        "/tipologias": {
          "valor": [ { "dormitorios": 1, "superficie_util_m2": 48.2, "renta_mensual_eur": 512.0, "…": "…" } ],
          "motivo": "Tabla en imagen escaneada",
          "autor": "github-handle",
          "fecha": "2026-11-27",
          "fuente_sha256": "9f2c…"
        }
      },
      "ocultar": false,
      "nota_publica": null
    }
  },
  "promociones_manuales": [
    { "…": "objeto Promocion completo que cumple promocion.schema.json, para fuentes sin scraper" }
  ]
}
```

**Reglas de fusión** (`core/merge.py`, función pura y testeada):

1. Base = unión de `data/sources/*.json` + `promociones_manuales`.
2. Para cada `id` con override se aplica cada JSON Pointer **sobre** el valor scrapeado. El override gana siempre.
3. Los arrays (`/tipologias`, `/enlaces/bases`) **solo se sustituyen enteros**. Se prohíben punteros con índice (`/tipologias/0/...`), y el schema de overrides lo valida con regex. Así se evita que un reordenamiento en origen aplique la corrección a la fila equivocada.
4. Si `fuente_sha256` ≠ hash actual del PDF principal, el override **se sigue aplicando**, pero se marca como `override-stale` y abre un issue: "la fuente cambió desde tu corrección, revísala". Nunca se descarta automáticamente.
5. `ocultar: true` saca la promoción de la web sin borrarla (útil para duplicados o falsos positivos).
6. Un override cuyo `id` ya no existe en ninguna fuente produce un *warning* en el informe, no un error.
7. Los campos con override se añaden a `meta.campos_override`, salen de `meta.campos_pendientes` y en `meta.procedencia` llevan `metodo: "override"`.

**Flujo humano de corrección:** se edita `overrides.json` desde la UI de GitHub o con un PR → `ci.yml` valida el schema → merge → `deploy.yml`. El issue de revisión trae el bloque JSON listo para pegar (§4.1).

### 3.4 `data/state.json`

```json
{
  "schema_version": 1,
  "ultima_ejecucion": "2026-11-27T05:21:44Z",
  "fuentes": {
    "emvs-madrid": {
      "estado": "ok",
      "ultima_ejecucion": "2026-11-27T05:20:10Z",
      "ultimo_exito": "2026-11-27T05:20:10Z",
      "fallos_consecutivos": 0,
      "ultimo_error": null,
      "promociones_vistas": 14,
      "duracion_s": 38.2
    }
  },
  "documentos": {
    "<sha1 de la URL canónica>": {
      "url": "https://…/bases.pdf",
      "tipo": "pdf",
      "fuente_id": "emvs-madrid",
      "promo_ids": ["emvs-madrid-madrid-vallecas-ensanche-34"],
      "etag": "\"abc123\"",
      "last_modified": "Tue, 25 Nov 2026 10:00:00 GMT",
      "sha256_bytes": "…",
      "sha256_texto": "…",
      "primera_vez": "2026-10-02",
      "ultimo_cambio": "2026-11-25",
      "ultima_comprobacion": "2026-11-27",
      "extractor_version": "1.3.0",
      "ocr_necesario": false
    }
  },
  "promo_ids": { "<URL canónica de la ficha>": "emvs-madrid-madrid-vallecas-ensanche-34" }
}
```

**Detección de cambios en dos niveles:**
- **HTML:** se hashea solo el **fragmento relevante** (selector CSS definido por el adaptador), tras normalizarlo: quitar scripts, tokens CSRF, fechas de "visitado" y espacios. Hashear la página entera daría falsos positivos a diario.
- **PDF:** `sha256_bytes` sirve como cortocircuito. Si cambian los bytes pero no `sha256_texto` (texto normalizado), es un PDF regenerado con otros metadatos y **no** se reextrae.
- **Reextracción forzada:** si `extractor_version` del documento < versión actual del paquete, se reparsea aunque el hash no cambie. Así una mejora de regex se aplica a todo el histórico sin volver a descargar (los PDFs se cachean en `actions/cache`, §4.1).

### 3.5 `data/iprem.json`

```json
{
  "$schema": "./schema/iprem.schema.json",
  "schema_version": 1,
  "nota": "Actualizar cada enero tras la Ley de PGE o su prórroga. Fuente: BOE / SEPE.",
  "valores": [
    { "anio": 2023, "mensual": 600.00, "anual_12": 7200.00, "anual_14": 8400.00, "fuente": "Ley 31/2022 PGE 2023", "verificado": true },
    { "anio": 2024, "mensual": 600.00, "anual_12": 7200.00, "anual_14": 8400.00, "fuente": "PGE 2023 prorrogados", "verificado": true },
    { "anio": 2025, "mensual": 600.00, "anual_12": 7200.00, "anual_14": 8400.00, "fuente": "PGE 2023 prorrogados", "verificado": true },
    { "anio": 2026, "mensual": 600.00, "anual_12": 7200.00, "anual_14": 8400.00, "fuente": "PGE 2023 prorrogados (confirmar en BOE)", "verificado": false }
  ]
}
```

El schema exige `anual_12 == mensual × 12` y `anual_14 == mensual × 14`. Lo comprueba un test, porque JSON Schema no puede expresarlo. Si el año que pide la calculadora no está en la tabla, la UI usa el último disponible y muestra un aviso visible.

### 3.6 `data/programas.json` (reglas por defecto, versionadas por vigencia)

Las bases de cada convocatoria **prevalecen**. Este archivo solo da valores por defecto cuando la promoción no los trae, y la UI marca esos valores como "valor general del régimen, comprueba las bases".

```json
{
  "schema_version": 1,
  "programas": [
    {
      "clave": "VPPB",
      "tipo": "regimen",
      "vigente_desde": "2009-01-01",
      "vigente_hasta": null,
      "ingresos_min_iprem": null,
      "ingresos_max_iprem": 5.5,
      "iprem_pagas": 14,
      "tasa_esfuerzo_max": null,
      "empadronamiento": null,
      "coeficientes_ponderacion": null,
      "requisitos_no_comprobables": [
        "No ser titular de pleno dominio o derecho de uso de otra vivienda",
        "Destinar la vivienda a residencia habitual y permanente"
      ],
      "fuente": "Decreto 74/2009 (Reglamento VPP Comunidad de Madrid); sede.comunidad.madrid",
      "verificado": false
    },
    {
      "clave": "VPPL",
      "tipo": "regimen",
      "vigente_desde": "2009-01-01",
      "vigente_hasta": null,
      "ingresos_max_iprem": 7.5,
      "…": "…",
      "verificado": false
    },
    {
      "clave": "PLAN_VIVE",
      "tipo": "programa",
      "vigente_desde": null,
      "ingresos_min_iprem": null,
      "ingresos_max_iprem": null,
      "tasa_esfuerzo_max": 0.35,
      "…": "…",
      "verificado": false
    }
  ]
}
```

`vigente_desde` y `vigente_hasta` existen porque **en 2026 está en tramitación un nuevo Reglamento de VPP de la Comunidad de Madrid**. Las informaciones públicas apuntan a ingresos mínimos y a un periodo mínimo de empadronamiento. Al publicarse en el BOCM se añadirá una entrada nueva con su fecha, sin borrar la anterior, para que las promociones antiguas se sigan evaluando con su norma. Ver §6.4.

---

## 4. GitHub Actions

### 4.0 Consideraciones de plataforma que condicionan el diseño

| Hecho | Consecuencia de diseño |
|---|---|
| Un `push` hecho con `GITHUB_TOKEN` **no dispara** otros workflows. | `scrape.yml` llama a `deploy.yml` como **reusable workflow** (`workflow_call`) en un job posterior. No se depende del evento `push`. |
| GitHub **desactiva los cron** de repos públicos sin actividad durante 60 días. | El commit diario de `state.json` (última comprobación) mantiene el repo activo. Además se añade una alerta (§4.1, paso 9) si el cron deja de ejecutarse. |
| El cron de Actions puede ir con retraso o saltarse ejecuciones en horas punta. | Se programa en un minuto no redondo (`23 4 * * *` UTC ≈ 05:23/06:23 Madrid). Se tolera la variación. |
| Los jobs duran como máximo 6 h y los runners son efímeros. | `timeout-minutes: 45` global y timeout por fuente dentro de Python. |
| Concurrencia: dos ejecuciones podrían pisarse al hacer push. | `concurrency: group: scrape, cancel-in-progress: false` + `git pull --rebase` con reintentos antes del push. |

### 4.1 `scrape.yml` — diseño

```yaml
name: scrape
on:
  schedule: [{ cron: "23 4 * * *" }]
  workflow_dispatch:
    inputs:
      fuentes:      { description: "IDs separados por coma (vacío = todas)", required: false }
      forzar_reparse: { type: boolean, default: false }

permissions:
  contents: write     # commit de data/
  issues: write       # issues de revisión

concurrency: { group: scrape, cancel-in-progress: false }

jobs:
  scrape:
    runs-on: ubuntu-latest
    timeout-minutes: 45
    outputs:
      changed: ${{ steps.commit.outputs.changed }}
    steps:
      # 1. checkout (fetch-depth: 1)
      # 2. setup-python 3.12 + cache de uv
      # 3. cache Playwright (~/.cache/ms-playwright) con clave = versión de playwright
      #    → `playwright install --with-deps chromium` solo si cache miss
      # 4. cache de PDFs descargados (clave: hash de state.json; restore-keys parciales)
      # 5. python -m vpo run --fuentes "$INPUT" [--forzar-reparse]
      #       - orquestador: cada fuente en try/except + timeout propio (por defecto 5 min)
      #       - escribe data/sources/<id>.json SOLO si la fuente terminó OK
      #       - si falla: conserva el archivo anterior, marca estado=error en state.json
      #       - exit code 0 aunque fallen fuentes; ≠0 solo ante error global (schema roto, bug)
      # 6. python -m vpo merge      → data/promociones.json (aplica overrides)
      # 7. python -m vpo validate   → JSON Schema de todo data/ ; si falla, aborta SIN commit
      # 8. python -m vpo review sync-issues   (usa `gh`, env GH_TOKEN=${{ github.token }})
      # 9. python -m vpo review health        → issue "scraper-broken" por fuente con ≥3 fallos seguidos
      # 10. commit (id: commit):
      #       git add data/promociones.json data/state.json data/sources/
      #       si no hay diff → changed=false
      #       si hay diff → commit "data: scrape YYYY-MM-DD (N cambios, M pendientes)"
      #                     autor github-actions[bot]; push con 3 reintentos + pull --rebase
      # 11. job summary ($GITHUB_STEP_SUMMARY): tabla de fuentes, cambios y pendientes

  deploy:
    needs: scrape
    if: needs.scrape.outputs.changed == 'true'
    uses: ./.github/workflows/deploy.yml
    permissions: { pages: write, id-token: write, contents: read }
```

**Aislamiento de errores por fuente** (dentro de `vpo run`):

```
para cada fuente activa en fuentes.json:
    inicio = now
    try (timeout = fuente.timeout_s):
        listado   = adapter.listar()            # HTML del listado → URLs de fichas
        for ficha in listado:                   # error en UNA ficha no tumba la fuente
            try: promo = adapter.parsear_ficha(ficha)
                 docs  = adapter.documentos(ficha)      # PDFs de bases
                 for doc in docs: if cambió(doc) or reparse: extraction.pipeline(doc) → fusiona en promo
            except: registra error de ficha, conserva versión previa de esa promo
        if errores_ficha / total > 50 %: estado = "degradado"
        escribe data/sources/<id>.json (atómico: tmp + rename)
    except Exception/Timeout:
        estado = "error"; fallos_consecutivos += 1; NO toca sources/<id>.json
    finally:
        actualiza state.fuentes[id]
```

- **Promociones desaparecidas:** si una promoción no aparece en el listado de origen, `activa_en_fuente = false` y conserva sus datos. A los 30 días sin verse, `estado = finalizada` si no lo estaba ya. Nunca se borra (sirve de histórico).
- **Cortesía con los servidores:** User-Agent genérico (`vpo-madrid-bot/1.0 (+https://<usuario>.github.io/<repo>/metodologia)`), sin datos personales. Se respeta `robots.txt`, 1 petición cada 2–3 s por host, peticiones condicionales (`If-None-Match` / `If-Modified-Since`) y máximo 3 reintentos con backoff exponencial en 5xx/429.

**Gestión de GitHub Issues** (`review/issues.py`):

| Tipo | Etiqueta | Clave de deduplicación (comentario oculto en el body) | Se abre cuando | Se cierra cuando |
|---|---|---|---|---|
| Revisión de datos | `needs-review` | `<!-- vpo:review:<promo_id> -->` | `campos_pendientes` no está vacío tras merge | `campos_pendientes` queda vacío (por override o reextracción): cierre automático con comentario |
| Override desfasado | `override-stale` | `<!-- vpo:stale:<promo_id> -->` | `fuente_sha256` del override ≠ hash actual | Se actualiza el `fuente_sha256` del override |
| Fuente rota | `scraper-broken` | `<!-- vpo:source:<fuente_id> -->` | `fallos_consecutivos ≥ 3` o `degradado` 3 días | Primera ejecución OK |
| Cron parado | `infra` | `<!-- vpo:heartbeat -->` | (lo abre `ci.yml` semanal si `ultima_ejecucion` > 3 días) | Ejecución OK |

- Búsqueda: `gh issue list --label needs-review --state open --search "vpo:review:<id> in:body" --json number,body`.
- Si existe, **se edita el body** (`gh issue edit`) en lugar de añadir comentarios cada día. Solo se comenta cuando cambia el conjunto de campos pendientes, para no generar ruido.
- **Contenido del issue de revisión:**
  - Promoción, operador, enlace a la ficha oficial y al PDF (con página).
  - Tabla `campo | motivo (no_encontrado / conflicto / fuera_de_rango / pdf_escaneado) | candidatos encontrados con página y fragmento`.
  - **Bloque JSON listo para pegar** en `overrides.json` con `fuente_sha256` ya relleno.
  - Enlace para editar `overrides.json` en la UI de GitHub.
- **Límite anti-avalancha:** máximo 20 issues nuevos por ejecución. El exceso va a un único issue resumen.

### 4.2 `deploy.yml` — diseño

```yaml
name: deploy
on:
  push:
    branches: [main]
    paths: ["web/**", "data/**", "!data/sources/**"]   # cambios humanos (overrides, web)
  workflow_dispatch:
  workflow_call:                                        # invocado por scrape.yml

permissions: { contents: read, pages: write, id-token: write }
concurrency: { group: pages, cancel-in-progress: false }

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      # checkout → setup-node 22 (cache npm, working-directory web)
      # npm ci
      # npm run validate-data   (Ajv contra data/schema/*; falla el build si no cuadra)
      # npm test                (vitest: eligibility.ts, filters.ts)
      # npm run build           (astro build → web/dist)
      #    - genera también dist/data/index.json "ligero" (lo que necesita el buscador)
      # actions/configure-pages
      # actions/upload-pages-artifact (path: web/dist)
  deploy:
    needs: build
    environment: { name: github-pages, url: ${{ steps.d.outputs.page_url }} }
    runs-on: ubuntu-latest
    steps:
      # actions/deploy-pages (id: d)
```

Ajuste del repositorio: *Settings → Pages → Source: GitHub Actions*.

### 4.3 `ci.yml` (en PR y push no-bot)

- `pytest` (reglas, merge y golden tests) + `vitest` + validación de schema de **todo** `data/`.
- **Guardia de propiedad de archivos:** si el autor del commit es `github-actions[bot]` y el diff toca `overrides.json`, `iprem.json`, `programas.json`, `fuentes.json` o `municipios.json`, falla.
- **Heartbeat semanal** (`schedule` lunes): si `state.ultima_ejecucion` tiene más de 3 días, abre el issue `infra`.

---

## 5. Estrategia de extracción determinista

### 5.1 Interfaz desacoplada (contrato, no implementación)

```
Document
  url, tipo (pdf|html), sha256, paginas: [ {numero, texto, bloques[(bbox, texto)], tablas[[[celda]]]} ],
  secciones: { "requisitos": (pag_ini, pag_fin, texto), "rentas": …, "plazos": … }

FieldResult
  campo (JSON Pointer), valor, confianza ∈ [0,1], pagina, evidencia (≤400 chars), regla (ID), metodo

ExtractionResult
  campos: [FieldResult], advertencias: [str], necesita_ocr: bool

Protocol Extractor
  nombre: str
  version: str
  campos_soportados: set[str]
  extract(doc: Document, ctx: ExtractionContext) -> list[FieldResult]

ExtractionContext
  fuente_id, promo_parcial (lo ya sacado del HTML), municipio_ine, programa_hint, fecha_ref
```

`pipeline.py`:
1. Construye `Document` (PDF o HTML) y preprocesa (§5.2).
2. Ejecuta **todos** los extractores registrados que declaran el campo (`RulesExtractor` hoy; `LLMExtractor` mañana, activado por la variable de entorno `VPO_LLM=on`).
3. **Resolución por campo:** agrupa candidatos y aplica:
   - Un único valor con confianza ≥ **umbral del campo** (configurable; por defecto 0,8) → se acepta.
   - Varios valores **distintos** con confianza ≥ 0,5 → `null` + motivo `conflicto` (se listan todos en el issue).
   - Valor fuera de rango plausible (`validators.py`) → se descarta y motivo `fuera_de_rango`.
   - Nada → `null` + motivo `no_encontrado`.
4. Validaciones de coherencia entre campos: `inscripcion_inicio ≤ inscripcion_fin`; `min_iprem < max_iprem`; renta de 3D ≥ renta de 1D (si no se cumple, se baja la confianza de toda la tabla); `tasa_esfuerzo` entre 0,2 y 0,5.
5. Devuelve `ExtractionResult`. El adaptador de la fuente lo fusiona con lo sacado del HTML, con esta **prioridad: HTML estructurado > tabla PDF > texto PDF**.

> **Enchufe LLM futuro:** `extraction/llm/llm_extractor.py` implementaría el mismo `Protocol` y recibiría solo la sección relevante (`doc.secciones[...]`) para minimizar tokens. Sus `FieldResult` llevarían `metodo: "llm"` y confianza máxima de 0,7, de modo que **nunca gane a una regla determinista que coincida** y solo rellene huecos. Por eso la arquitectura de umbrales y conflictos ya está pensada para varias fuentes de candidatos.

### 5.2 Preprocesado del texto PDF

1. **Detección de PDF escaneado:** si hay menos de 50 caracteres extraíbles por página de media, `necesita_ocr = true` → todos los campos a `null` + issue con motivo `pdf_escaneado`. El OCR (Tesseract, gratis) queda como **mejora opcional en Fase 5+**, siempre con confianza ≤ 0,6.
2. Normalización Unicode **NFKC**: ligaduras `ﬁ`→`fi` y comillas tipográficas.
3. Deshifenado: `vivien-\nda` → `vivienda`. Se unen saltos de línea dentro de párrafo y se conservan los dobles.
4. Se colapsan espacios y se eliminan cabeceras y pies repetidos (líneas idénticas en más del 60 % de páginas).
5. Se crea una **copia en minúsculas sin tildes** para buscar, manteniendo un mapeo de offsets al texto original para poder citar la evidencia literal.
6. **Segmentación por secciones** con títulos típicos de bases ("REQUISITOS", "BASE n.ª", "RÉGIMEN ECONÓMICO", "RENTA", "PLAZO DE PRESENTACIÓN", "ANEXO"). Las reglas buscan **primero en su sección** (confianza +0,1) y luego en el documento completo.
7. **Lista negra de contexto:** párrafos que citan normativa genérica ("de conformidad con el Decreto…", "artículo X del Reglamento…") reciben una penalización de −0,3. Así se evita capturar umbrales de otras modalidades citadas de pasada.

### 5.3 Catálogo de patrones (sobre texto normalizado sin tildes y en minúsculas)

**Números en formato español** (helper común `NUM`):
`(?P<n>\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:,\d+)?)` → `"1.234,56"` → `1234.56`.
Palabras → número: `un|una|uno=1, dos=2, tres=3, cuatro=4, cinco=5, seis=6, diez=10` (`normalize.py`).

**Ingresos / IPREM**

| ID | Patrón (esquema) | Captura | Confianza base |
|---|---|---|---|
| REG-IPREM-01 | `(?:no\s+(?:super(?:ar|en|e)|exced(?:er|an|a))|inferiores?\s+a|hasta|maxim[oa]s?\s+de)\s+(?:de\s+)?{NUM}\s*(?:veces|x)\s+(?:el\s+)?(?:iprem\|indicador publico de renta de efectos multiples)` | `ingresos_max_iprem` | 0,85 |
| REG-IPREM-02 | `(?:no\s+inferiores?\s+a\|minim[oa]s?\s+de\|superiores?\s+a\|al\s+menos)\s+{NUM}\s*(?:veces\|x)\s+(?:el\s+)?iprem` | `ingresos_min_iprem` | 0,85 |
| REG-IPREM-03 | `entre\s+{NUM}\s+y\s+{NUM}\s+veces\s+(?:el\s+)?iprem` | min y max | 0,9 |
| REG-IPREM-04 | Tabla (pdfplumber) con cabecera que contiene `miembros` y `iprem`: cada fila → `ingresos_por_miembros[]` | tabla escalonada | 0,9 |
| REG-IPREM-05 | `iprem.{0,40}?(?P<pagas>12\|catorce\|14)\s+pagas` | `iprem_pagas` | 0,9 |
| REG-IPREM-06 | `(?:ejercicio\|declaracion\s+(?:de\s+)?(?:la\s+)?renta\|irpf)\s+(?:de(?:l)?\s+)?(?:ano\s+)?(?P<y>20\d{2})` | `iprem_ejercicio` | 0,7 |

Si aparece el `NUM` sin contexto min/max, se descarta (no se adivina).

**Tasa de esfuerzo**
- REG-ESF-01: `(?:la\s+renta|el\s+alquiler).{0,80}?no\s+(?:podra\s+)?super(?:ar|e)\s+(?:el\s+)?(?P<p>\d{1,2})\s*(?:%|por\s*ciento)\s+de\s+(?:los\s+)?ingresos` → `tasa_esfuerzo_max = p/100` (0,85).
- REG-ESF-02: `tasa\s+de\s+esfuerzo.{0,40}?(?P<p>\d{1,2})\s*%` (0,8).

**Empadronamiento**
- REG-EMP-01: `empadronad[oa]s?\s+(?:en\s+(?:el\s+municipio\s+de\s+)?(?P<mun>[a-z\s\-]+?))?.{0,80}?(?:con\s+(?:una\s+)?antiguedad\s+(?:minima\s+)?de\s+|durante\s+(?:al\s+menos\s+)?|al\s+menos\s+)(?P<n>\d+|un|uno|dos|tres|cuatro|cinco|diez)\s+anos?` → `anios_min`, `municipio` (resuelto a INE con `municipios.json`; si no resuelve → `null`).
- REG-EMP-02: `de\s+forma\s+(?:ininterrumpida|continuada)|inmediatamente\s+anteriores?` en ±150 caracteres → `ininterrumpido = true`.
- REG-EMP-03: `(?:empadronad[oa]s?|residir)\s+(?:o|y/o)\s+(?:desarrollar\s+(?:su\s+)?actividad\s+laboral|trabajar)` → `alternativa_trabajo = true`.
- REG-EMP-04: `comunidad\s+de\s+madrid` como objeto del empadronamiento → `ambito = comunidad`.
- Si se detecta "empadronado" pero no los años → `empadronamiento` con `anios_min = null` → campo pendiente.

**Rentas**
- REG-RENTA-01 (tabla): cabeceras con `dormitorios|tipologia|n.º dorm` y `renta|alquiler|precio` → cada fila → `tipologia`. Columnas opcionales `superficie|m2|util`, `garaje`, `trastero`, `n.º viviendas`.
- REG-RENTA-02 (texto): `(?P<d>\d|un|dos|tres|cuatro)\s*(?:dormitorios?|dorm\.?|d\b).{0,60}?{NUM}\s*(?:€|euros)(?:\s*(?:/|al|por)\s*mes|\s*mensuales)?`.
- REG-RENTA-03 (horquilla): `desde\s+{NUM}\s*(?:€|euros).{0,20}?hasta\s+{NUM}\s*(?:€|euros)`.
- REG-RENTA-04 (€/m²): `{NUM}\s*(?:€|euros)\s*/\s*m2(?:\s*util)?` → se guarda en evidencia **solo si** existe superficie para calcular. Si no, no se infiere renta.
- Marcadores de IVA y gastos: `(?:iva\s+(?:no\s+)?incluido|mas\s+iva|gastos\s+de\s+comunidad\s+(?:no\s+)?incluidos)` → nota en `otros`. Las rentas siempre se guardan **tal como aparecen** y no se recalculan impuestos.
- Rango plausible: 150–2.500 €/mes. Fuera de él → descartado.

**Fechas**
- REG-FECHA-01: `(?P<d>\d{1,2})\s+de\s+(?P<m>enero|febrero|marzo|abril|mayo|junio|julio|agosto|se(?:p)?tiembre|octubre|noviembre|diciembre)\s+de(?:l)?\s+(?P<y>20\d{2})`.
- REG-FECHA-02: `(?P<d>\d{1,2})[/\-.](?P<m>\d{1,2})[/\-.](?P<y>20\d{2})` (siempre d/m/a).
- REG-FECHA-03 (rango): `(?:del|desde\s+el)\s+{FECHA}\s+(?:al|hasta\s+el)\s+{FECHA}` → `inscripcion_inicio` y `inscripcion_fin` si la ventana previa (−200 caracteres) contiene `plazo|presentacion|solicitudes|inscripcion`.
- REG-FECHA-04 (plazo relativo): `(?P<n>\d+|quince|veinte|treinta)\s+dias\s+(?:habiles|naturales)\s+(?:a\s+contar\s+)?desde` → **no** se calcula la fecha (depende de festivos y de la fecha de publicación) → `null` + evidencia en el issue.
- Palabras de contexto para clasificar una fecha suelta: `sorteo`→`sorteo`, `entrega|llaves|finalizacion\s+de\s+obras`→`entrega_prevista`.
- Plausibilidad: fecha_ref − 3 años ≤ fecha ≤ fecha_ref + 5 años.

**Edad**
- REG-EDAD-01: `menores\s+de\s+(?P<max>\d{2})\s+anos` → `max = max − 1`. Se documenta la semántica: "menor de 35" equivale a ≤ 34 años cumplidos.
- REG-EDAD-02: `(?:edad\s+)?(?:comprendida\s+)?entre\s+(?P<min>\d{2})\s+y\s+(?P<max>\d{2})\s+anos`.
- REG-EDAD-03: `mayores\s+de\s+(?P<min>\d{2})`.
- Si aparece `cupo|reserva|porcentaje\s+de\s+viviendas` en ±200 caracteres → `tipo = cupo`. Si no → `requisito`.

**Garaje / trastero**
- REG-ANEJO-01: `(?:plaza\s+de\s+)?(?P<a>garaje|aparcamiento|trastero)s?.{0,60}?(?P<k>incluid[oa]s?|vinculad[oa]s?|anej[oa]s?)` → `incluido`.
- REG-ANEJO-02: `…(?P<k>opcional|no\s+vinculad[oa]|podra\s+alquilarse)` → `opcional`.
- REG-ANEJO-03: `…{NUM}\s*(?:€|euros)` cerca de `garaje|trastero` → `precio_mensual_eur`.
- Si no se menciona nada → `desconocido`, **nunca** `no`. "No" solo se asigna con una negación explícita (`sin\s+garaje|no\s+dispone`).

**Estado (desde HTML principalmente)**
Diccionario por fuente en el adaptador, más reglas genéricas: `proximamente|en\s+construccion|proxima\s+apertura` → `proxima`; `abierto\s+(?:el\s+)?plazo|inscribete|solicitudes\s+abiertas` → `inscripcion_abierta`; `plazo\s+(?:cerrado|finalizado)` → `inscripcion_cerrada`; `sorteo|listado\s+(?:provisional|definitivo)` → `sorteo_adjudicacion`. Si `inscripcion_fin < hoy` y estado = `inscripcion_abierta`, se corrige a `inscripcion_cerrada` en el merge (regla derivada, con `metodo: html` + nota).

### 5.4 Calidad y regresión

- **Golden tests:** cada PDF de `tests/fixtures/pdf/` tiene su `tests/golden/<nombre>.json` con los `FieldResult` esperados (valor + regla). Cambiar un patrón exige que todos los golden pasen o actualizarlos en el mismo PR con justificación.
- **Métricas** en un test parametrizado que imprime una tabla: precisión (aciertos/extraídos) y cobertura (extraídos/esperados) por campo. **Objetivo: precisión ≥ 0,98**, con cobertura ≥ 0,7 como meta y sin bloquear.
- `extractor_version` sigue SemVer: patch para nuevos sinónimos, minor para nueva regla y major para cambio de semántica de un campo. Cualquier cambio de minor o superior fuerza el reparseo en la siguiente ejecución (§3.4).

---

## 6. Reglas de negocio de la calculadora

### 6.1 Entradas (formulario, nada se persiste)

| Campo | Tipo | Notas de UI |
|---|---|---|
| `ingresos_anuales` | € | **Etiqueta:** "Ingresos de la unidad de convivencia (IRPF)". Ayuda: en Madrid se usa normalmente la **suma de la base imponible general y del ahorro** de la última declaración de todos los miembros, no el salario bruto. Se ofrece un conmutador "solo sé mi bruto anual" que aplica una **estimación orientativa** (bruto − cotizaciones SS ≈ 6,35 % − 2.000 € de gastos deducibles), marcada siempre como aproximación. Se enlaza al manual oficial de la calculadora de la CAM. |
| `ejercicio` | año | Por defecto, año actual − 1. Sirve para elegir el IPREM. |
| `miembros` | 1–10 | Unidad de convivencia. |
| `municipio_empadronamiento` + `anios_empadronamiento` | INE + número | Autocompletado con `municipios.json`. |
| `municipio_trabajo` + `anios_trabajo` | INE + número (opcional) | Para reglas con `alternativa_trabajo`. |
| `edad` | 16–100 | Del solicitante principal. |
| `titular_vivienda` | sí/no | Para el requisito habitual de no titularidad. |
| `dormitorios_min` | opcional | Filtro de preferencia, no de elegibilidad. |

**Privacidad:** el estado vive solo en memoria del componente. Sin `localStorage`, sin parámetros de URL y sin enviar nada a la red. La página no hace ninguna petición tras cargar `index.json`.

### 6.2 Resolución de parámetros (por promoción)

Para cada parámetro `p`:

```
valor(p) = promocion.requisitos[p]                     si ≠ null   → origen "bases"
         ∨ programas[programa vigente en fecha_ref][p]  si ≠ null   → origen "general_programa"
         ∨ programas[regimen vigente en fecha_ref][p]   si ≠ null   → origen "general_regimen"
         ∨ null                                                     → origen "desconocido"
```

`fecha_ref` = `fechas.inscripcion_inicio` ∨ `meta.primera_deteccion`, y se usa para elegir la versión vigente del programa. El origen se muestra en la UI junto a cada comprobación.

### 6.3 Evaluación

Definiciones:
- `IPREM_anual = iprem[ejercicio][requisitos.iprem_pagas ?? 14 → anual_14 | anual_12]`. Por defecto **14 pagas**, que es lo habitual en la normativa de vivienda madrileña. Si las bases dicen otra cosa, prevalecen.
- `veces_iprem = ingresos_ponderados / IPREM_anual`.
- `ingresos_ponderados = ingresos_anuales × coef(miembros)` si el programa define `coeficientes_ponderacion`. Si no, `= ingresos_anuales`.

Cada regla devuelve `CUMPLE | NO_CUMPLE | DESCONOCIDO | INFORMATIVO` con una explicación legible:

| # | Regla | Lógica |
|---|---|---|
| R1 | Ingresos máximos | Si `ingresos_por_miembros` ≠ null → fila donde `miembros_desde ≤ miembros ≤ (miembros_hasta ?? ∞)`. Si no, `max_iprem`. `veces_iprem ≤ max` → CUMPLE. |
| R2 | Ingresos mínimos | Ídem con `min`. `veces_iprem ≥ min` → CUMPLE. Si `ingresos_min_iprem` está en `no_exigidos` → CUMPLE; si es `null` y no está → DESCONOCIDO. |
| R3 | Tasa de esfuerzo | Por **tipología**: `renta_mensual_eur × 12 / ingresos_anuales ≤ tasa_esfuerzo_max`. La promoción CUMPLE si **al menos una tipología** cumple, y la UI indica cuáles. Si la renta es `null` → DESCONOCIDO. Equivale a un ingreso mínimo implícito: `ingreso_min = renta × 12 / tasa`, que se muestra como "necesitas al menos X €/año para la vivienda de N dormitorios". |
| R4 | Empadronamiento | En `no_exigidos` → CUMPLE. `empadronamiento = null` y no listado → DESCONOCIDO. `ambito = comunidad` → basta cualquier municipio `28xxx` con `anios ≥ anios_min`. `ambito = municipio` → `municipio_empadronamiento == municipio_ine ∧ anios ≥ anios_min`, **o** (si `alternativa_trabajo`) `municipio_trabajo == municipio_ine ∧ anios_trabajo ≥ anios_min`. `anios_min = null` → DESCONOCIDO. |
| R5 | Edad | `tipo = requisito`: `min ≤ edad ≤ max` → CUMPLE/NO_CUMPLE. `tipo = cupo`: siempre INFORMATIVO ("optas al cupo de jóvenes" o "optas al cupo general"). |
| R6 | No titularidad | `no_titular_vivienda ≠ false ∧ usuario.titular` → NO_CUMPLE con matiz "salvo excepciones de las bases (separación, vivienda inadecuada…)". |
| R7 | Estado | `finalizada` → la promoción se excluye del resultado por defecto (con conmutador "mostrar finalizadas"). `proxima` → INFORMATIVO "aún no abre". |
| R8 | Adecuación tipología/miembros | Solo si el programa define `adecuacion` (p. ej. máximo de miembros por dormitorio). Si no, no se evalúa. |
| R9 | Requisitos no comprobables | `requisitos.otros` + `requisitos_no_comprobables` del programa → lista "también debes cumplir". |

**`null` y `no_exigidos` (ADR-001 §1):** un requisito en `null` es siempre *desconocido* y da DESCONOCIDO. Solo lo que figura en `requisitos.no_exigidos` cuenta como no exigido. Esto vale también para R5, R6 y la tasa de esfuerzo.

**Resultado agregado por promoción:**
- **Elegible:** todas las reglas en CUMPLE o INFORMATIVO.
- **Posiblemente elegible:** ninguna en NO_CUMPLE y al menos una en DESCONOCIDO, o algún parámetro con origen `general_*` cuyo programa tiene `verificado: false`.
- **No elegible:** al menos una en NO_CUMPLE (se muestra la primera causa).

Orden: elegibles > posiblemente > no elegibles. Dentro de cada grupo, `inscripcion_abierta` primero y luego por renta ascendente.

**Invariantes testeados** (vitest, tabla de casos): fronteras exactas (`veces_iprem == max` → CUMPLE), años de empadronamiento decimales, `menores de 35` con 34 → CUMPLE y con 35 → NO_CUMPLE, IPREM de un año ausente → aviso, y todas las combinaciones de `null`.

### 6.4 Valores de partida y tareas de verificación (Fase 1)

| Parámetro | Valor de partida | Estado |
|---|---|---|
| IPREM 2023–2025 | 600 €/mes · 7.200 €/año (12 pagas) · 8.400 €/año (14 pagas) | Confirmado |
| IPREM 2026 | Igual (PGE 2023 prorrogados) | **Confirmar en BOE** antes de publicar |
| VPPB/VPPA: ingresos máx. | 5,5 × IPREM | Coincide con la sede de la CAM y un BOCM de mar-2026. Confirmar la modalidad de arrendamiento |
| VPPL: ingresos máx. | 7,5 × IPREM | Ídem |
| Plan Vive: tasa de esfuerzo | 35 % (dato del enunciado) | **Sin verificar.** Comprobar en los pliegos o bases del Plan Vive |
| Nuevo Reglamento VPP CAM (2026) | Ingresos mínimos (~1,5 IPREM para 2 miembros según prensa) y empadronamiento mínimo | **En tramitación.** Añadir como nueva versión en `programas.json` cuando se publique en el BOCM |
| EMVS Madrid | Empadronamiento en Madrid capital, mín./máx. de IPREM y cupos | Varía por convocatoria. Tomar siempre de las bases; sin default |

Toda entrada con `verificado: false` provoca en la UI una insignia "valor general sin verificar" junto a la regla afectada.

---

## 7. Web: comportamiento y trazabilidad

### 7.1 Páginas
- **`/`** (buscador): tarjetas con filtros en cliente por municipio (multi), régimen/programa, estado, renta (rango con slider sobre la renta mínima de las tipologías), dormitorios (≥ N), garaje (incluido/opcional), trastero y "solo con inscripción abierta". Los filtros se reflejan en la URL (`?mun=28079&estado=inscripcion_abierta`), lo cual es aceptable porque **no** son datos personales. Hay orden por renta, fecha de cierre o novedad.
- **`/promociones/[id]`** (ficha estática): datos, tabla de tipologías, requisitos con su origen (bases / general / desconocido), fechas y bloque **Trazabilidad**:
  - Enlace oficial (botón primario).
  - PDF(s) de bases enlazados **a la URL original**, con fecha de detección y hash corto.
  - "Última comprobación: dd/mm/aaaa" (de `state.json`) y "Datos modificados por última vez: dd/mm/aaaa".
  - Campos corregidos manualmente marcados con un icono y tooltip con el motivo.
  - Campos pendientes como "Dato no disponible: consulta las bases".
  - Enlace "¿Ves un error?" que abre un issue con la plantilla `correccion-dato.yml` y el `id` prerrellenado.
- **`/calculadora`**: formulario y lista de resultados con el desglose de reglas por promoción.
- **`/fuentes`**: estado de cada fuente (ok, degradada o error y última ejecución correcta).
- **`/metodologia`** y **`/aviso-legal`**.

### 7.2 Datos en cliente
En build se genera `dist/data/index.json` con solo los campos que usan buscador y calculadora (≈ 1–2 KB por promoción). Con unos cientos de promociones pesa menos de 300 KB sin comprimir, así que el filtrado en memoria es instantáneo y no hace falta índice de búsqueda externo. Si la búsqueda por texto lo necesita, se puede añadir más adelante Pagefind, que es estático y gratis.

### 7.3 Accesibilidad y rendimiento
HTML semántico, formularios etiquetados, contraste AA y la página funciona sin JS para leer fichas (el buscador sin JS muestra la lista completa). Objetivo Lighthouse ≥ 95.

### 7.4 Aspectos legales
- Solo se publican **datos fácticos** (rentas, requisitos, fechas) y **enlaces**. No se rehospedan los PDFs ni se copian textos o imágenes de las operadoras.
- Los fixtures de tests (PDF/HTML reales) pueden versionarse como material de prueba. Si alguna operadora lo objeta, se sustituyen por fixtures sintéticos que reproduzcan la estructura.
- Aviso visible en todas las páginas: información orientativa, sin vínculo con las administraciones ni las operadoras, y la convocatoria oficial prevalece.
- Sin cookies ni analítica, así que no hace falta banner de cookies. Si en el futuro se quiere analítica, solo opciones sin cookies y agregadas.

---

## 8. Plan de implementación (Fases 1–5 para Claude Sonnet en Claude Code)

**Reglas generales para cada fase:**
- Empieza cada sesión con: *"Lee ARCHITECTURE.md y CLAUDE.md. Vamos a ejecutar la Fase N. No implementes nada fuera de su alcance."*
- Cada fase termina con: tests en verde, `python -m vpo validate` en verde y commit propio con su mensaje.
- Si Sonnet detecta que el diseño no encaja con la realidad (p. ej. una web exige otro enfoque), **lo anota en `docs/decisiones/ADR-NNN.md`** y pregunta antes de desviarse.

### Fase 1: Cimientos y contratos (sin red)
**Objetivo:** repo inicializado con los contratos de datos y verificaciones de negocio.
1. `git init`, `.gitignore`, `README.md`, `LICENSE` y **`CLAUDE.md`** (convenciones: idioma de dominio en español, código en inglés salvo nombres de campos del dominio; "null antes que adivinar"; prohibido escribir en archivos manuales desde el scraper).
2. Todos los JSON Schemas de `data/schema/` tal como §3.
3. Archivos manuales iniciales: `iprem.json`, `programas.json` (con `verificado: false`), `municipios.json` (179 municipios, de la relación oficial del INE), `fuentes.json` (inventario de fuentes con URL a confirmar), `overrides.json` vacío y `promociones.json` vacío válido.
4. Esqueleto del paquete `scraper/` con `pyproject.toml`, modelos Pydantic coherentes con el schema y CLI con subcomandos vacíos.
5. `core/merge.py` completo + `test_merge.py`: precedencia, arrays enteros, `ocultar`, override huérfano y override desfasado.
6. `ci.yml` con validación de schemas y pytest.
7. **Verificaciones documentales** (manuales o con búsqueda web): IPREM 2026 en BOE, límites VPPB/VPPL/VPPA, condiciones del Plan Vive y estado del nuevo Reglamento VPP. Se actualizan `verificado` y `fuente`.

**Hecho cuando:** `pytest` y la validación de schemas pasan en CI, y `merge` produce un `promociones.json` válido a partir de fixtures sintéticos.

### Fase 2: Núcleo de scraping y primeras 2 fuentes (solo HTML)
**Objetivo:** pipeline extremo a extremo con hashing y aislamiento, sin PDF todavía.
1. `core/http.py` (UA, rate limit por host, robots.txt, ETag, reintentos) y `core/hashing.py` (bytes + texto normalizado + fragmento HTML por selector).
2. `core/state.py` con escritura atómica e IDs congelados.
3. Interfaz `SourceAdapter` (`listar`, `parsear_ficha`, `documentos`, `selector_hash`) y registro.
4. Adaptadores **EMVS Madrid** y **Plan Vive (CAM)**: primero se inspecciona la web real, se guardan fixtures HTML y se escriben los tests contra los fixtures. Playwright **solo** si httpx no basta (documentarlo en el ADR).
5. Orquestador `vpo run` con aislamiento por fuente y ficha, timeouts, estados `ok/degradado/error` y conservación del último dato bueno.
6. Lógica de promociones desaparecidas (`activa_en_fuente` y 30 días).

**Hecho cuando:** `vpo run && vpo merge && vpo validate` en local produce datos reales válidos, un test simula la caída de una fuente y comprueba que la otra no se ve afectada, y la segunda ejecución sin cambios en origen no produce diff (salvo `ultima_comprobacion`).

### Fase 3: Extracción determinista de PDF y revisión manual
**Objetivo:** extraer requisitos y rentas de las bases y gestionar lo dudoso con issues.
1. `extraction/base.py` (interfaz §5.1) y `documents/pdf.py` (PyMuPDF + pdfplumber, detección de escaneados).
2. `preprocess.py` (§5.2) con tests unitarios de cada transformación.
3. Reglas en `rules/` con el catálogo §5.3, **una familia por commit**, cada una con tests de frases sueltas (positivos **y** negativos).
4. `pipeline.py`: resolución de conflictos, umbrales, validadores y coherencia.
5. Reunir **≥ 10 PDFs reales** de bases (EMVS, Plan Vive y 2–3 EMV municipales) en fixtures y escribir sus golden a mano. Informe de precisión y cobertura.
6. `review/report.py` + `review/issues.py` (crear, actualizar y cerrar con deduplicación, límite de 20 y bloque JSON listo para pegar) y plantillas `.github/ISSUE_TEMPLATE/`.
7. `extractor_version` y reparseo forzado.
8. `extraction/llm/README.md` con el contrato para el futuro, **sin código**.

**Hecho cuando:** precisión ≥ 0,98 en golden; un PDF con valores contradictorios produce `null` + issue con ambos candidatos; un override en un campo pendiente cierra el issue en la siguiente ejecución (probado con `gh` mockeado).

### Fase 4: Web estática y despliegue
**Objetivo:** sitio publicado en GitHub Pages con buscador y fichas.
1. Proyecto Astro en `web/` (Preact, Tailwind, `base` configurado) y `lib/data.ts` con Ajv (el build falla si los datos no validan).
2. Generación de `types.ts` desde los JSON Schema (script `npm run gen:types`).
3. `filters.ts` puro + tests e isla `Buscador.tsx` con estado en URL.
4. Página de ficha con bloque de **Trazabilidad** completo (§7.1) y origen de cada requisito.
5. Páginas `fuentes`, `metodologia` y `aviso-legal`.
6. `index.json` ligero en build.
7. `deploy.yml` (§4.2) y activación de Pages con origen "GitHub Actions".

**Hecho cuando:** la URL de Pages sirve el sitio, todas las fichas tienen enlace oficial, PDF y fecha de comprobación, Lighthouse ≥ 95 en `/` y en una ficha, y funciona en móvil.

### Fase 5: Calculadora, automatización diaria y ampliación de fuentes
**Objetivo:** calculadora completa, cron en producción y cobertura de operadoras.
1. `eligibility.ts` (§6.2–6.3) con **tabla de casos de test** que cubra cada regla, fronteras y `null`. Primero tests, luego implementación.
2. Isla `Calculadora.tsx` con la ayuda sobre base imponible frente a bruto, estimación orientativa marcada y desglose por promoción. Verificar en DevTools que no hay peticiones de red ni almacenamiento.
3. `scrape.yml` completo (§4.1): caches, job summary, commit con reintentos y llamada a `deploy.yml`. Lanzarlo con `workflow_dispatch` antes de activar el cron.
4. Heartbeat semanal en `ci.yml` y guardia de propiedad de archivos.
5. Nuevos adaptadores, **uno por PR**: Avalon/ConVive, Sogeviso, Culmia, EMV/EMSV municipales (Alcobendas, Getafe, Rivas, Fuenlabrada, Leganés, Alcorcón…) y cooperativas con web pública. Cada uno con fixtures y golden.
6. (Opcional) OCR con Tesseract para PDFs escaneados, confianza ≤ 0,6.
7. Revisión final de textos legales y `README` con "cómo corregir un dato" en 3 pasos.

**Hecho cuando:** 7 días seguidos de cron sin intervención, todos los fallos de fuente aparecen como issue y no como workflow rojo, y la calculadora pasa la tabla de casos.

---

## 9. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Cambio de HTML en una operadora | Aislamiento por fuente, último dato bueno conservado, issue `scraper-broken` a los 3 fallos y fixtures para reproducir. |
| Bloqueo por IP de los runners (WAF/Cloudflare) | Peticiones condicionales, baja frecuencia y UA honesto. Si persiste, la fuente pasa a `activa: false` en `fuentes.json` y se mantiene con `promociones_manuales`. Sin proxies de pago. |
| PDFs escaneados o con tablas en imagen | `null` + issue + override manual. OCR opcional más adelante. |
| Regex capta umbral de otra modalidad citada en la normativa | Prioridad de sección, penalización por contexto normativo, detección de conflictos y golden tests. |
| Cambio normativo (Reglamento VPP 2026) | `programas.json` versionado por vigencia y prevalencia siempre de las bases de la promoción. |
| El usuario interpreta la calculadora como dictamen | Estados "posiblemente elegible", origen de cada dato visible y avisos de "orientativo". |
| Cron desactivado o silencioso | Commit diario (actividad), heartbeat semanal e issue `infra`. |
| Crecimiento del repo | Solo JSON de texto, sin PDFs en `data/` (los fixtures de test son pocos y estables). |

---

## 10. Decisiones validadas (2026-11-27)

1. **Astro + Preact.**
2. **Repositorio `vpo-madrid`**, usuario de GitHub `ServerHeaven` (confirmado). GitHub Pages sin dominio propio: `base = /vpo-madrid/`.
3. **Calculadora:** base imponible IRPF como dato principal; bruto como estimación orientativa.
4. **Fixtures reales.** Nunca documentos con datos personales (listados de admitidos o adjudicatarios) y fuera de la licencia del código.
5. **Primeras fuentes:** EMVS Madrid y Plan Vive.

Las cuestiones abiertas tras la Fase 1 están en [docs/decisiones/ADR-001-huecos-del-diseno.md](docs/decisiones/ADR-001-huecos-del-diseno.md).
