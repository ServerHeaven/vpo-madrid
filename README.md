# vpo-madrid

Buscador de promociones de alquiler protegido (VPPB, VPPL, Plan Vive, promociones municipales) en la Comunidad de Madrid.

**Estado:** en construcción. Se leen las páginas HTML de EMSV Getafe, EMVS Madrid y del Plan Vive y se extraen requisitos y rentas de las bases en PDF. La web (buscador, fichas y calculadora orientativa) está en [web/](web/) y se publica en <https://serverheaven.github.io/vpo-madrid/>. La actualización diaria está preparada, pero [todavía no activada](#actualización-diaria).

La información es orientativa. No tenemos relación con las administraciones ni con las operadoras: la convocatoria oficial prevalece siempre.

## Cómo funciona
Los datos son ficheros JSON en [data/](data/). GitHub Actions publica con ellos una web estática; más adelante, un proceso diario los actualizará. No hay servidores, bases de datos ni datos personales de visitantes. El diseño completo está en [ARCHITECTURE.md](ARCHITECTURE.md).

## Cómo corregir un dato
Necesitas una fuente oficial que respalde el cambio. Si no quieres editar ficheros, usa el enlace «¿Ves un error?» de la ficha. Las issues y las pull requests son públicas: no incluyas datos personales.

**1. Localiza la promoción y el campo.** El `id` es la última parte de la dirección de la ficha (`/promociones/<id>/`). Los campos se nombran con su ruta dentro del dato, por ejemplo `/requisitos/ingresos_max_iprem` (mira [data/promociones.json](data/promociones.json)).

**2. Añade la corrección a [data/overrides.json](data/overrides.json)**, dentro de `"overrides"`:

```json
"id-de-la-promocion": {
  "campos": {
    "/requisitos/ingresos_max_iprem": {
      "valor": 5.5,
      "motivo": "Bases, página 4",
      "autor": "tu-usuario-de-github",
      "fecha": "2026-11-27",
      "fuente_sha256": null
    }
  },
  "ocultar": false,
  "nota_publica": null
}
```

**3. Envía una pull request.** CI comprueba el formato y, cuando llega a `main`, la web se vuelve a publicar. Las correcciones ganan siempre al scraper.

Detalles:
- `fuente_sha256`: el hash del PDF que revisaste, o `null` si no hay PDF. Si el PDF cambia, se avisa.
- Las listas (`/tipologias`, `/enlaces/bases`) se sustituyen enteras.
- Si el objeto padre es `null` (por ejemplo `empadronamiento`), corrige el objeto completo.
- Un requisito en `null` significa «no lo sabemos». Si consta que **no se exige**, déjalo en `null` y añádelo a `/requisitos/no_exigidos` (la lista se sustituye entera), por ejemplo `["empadronamiento"]`.

Los datos que no se han podido extraer de las bases con seguridad se publican como issues con la etiqueta `needs-review`, cada uno con el bloque listo para pegar.

## Desarrollo
### Scraper
Requiere [uv](https://docs.astral.sh/uv/).

```
cd scraper
uv sync
uv run python -m pytest
uv run python -m vpo run        # lee las webs; --fuentes emvs-madrid para una sola
uv run python -m vpo merge
uv run python -m vpo validate
uv run python -m vpo reparse    # vuelve a extraer todos los PDF
uv run python -m vpo review report       # escribe data/review-report.json
uv run python -m vpo review sync-issues  # crea y cierra issues; necesita `gh` autenticado
uv run python -m vpo review health       # issues de fuentes rotas
uv run python -m vpo review heartbeat    # issue si no hay lecturas desde hace más de 3 días
```

### Web
Requiere Node 22.23.4 o superior. Lee los datos de `data/`.

```
cd web
npm ci
npm run dev             # servidor de desarrollo, en la ruta /vpo-madrid/
npm run validate-data   # comprueba data/ contra los schemas
npm test
npm run check           # tipos
npm run build           # genera web/dist
npm run preview         # sirve web/dist
npm run gen:types       # tras cambiar un schema
```

## Actualización diaria
[scrape.yml](.github/workflows/scrape.yml) lee las fuentes, fusiona, valida, sincroniza las issues, hace commit de `data/` y vuelve a publicar la web. Solo actúa en `main`. Para activarlo:

1. En **Settings → Actions → General**, comprueba que los workflows pueden ejecutarse.
2. Lánzalo a mano: **Actions → scrape → Run workflow**.
3. Si termina bien, descomenta `schedule` en `scrape.yml` y actualiza la frase sobre la actualización diaria en la [página de metodología](web/src/pages/metodologia.astro).

Los lunes, [ci.yml](.github/workflows/ci.yml) abre una issue `infra` si hace más de 3 días que no hay lecturas (hasta activar la programación es de esperar que aparezca). El bot solo puede escribir `data/promociones.json`, `data/state.json` y `data/sources/`; lo comprueba `python -m vpo.guardia`.

## Publicación
[deploy.yml](.github/workflows/deploy.yml) aplica las correcciones (`vpo merge`, sin hacer commit), construye la web y la publica en <https://serverheaven.github.io/vpo-madrid/>. Se ejecuta al cambiar `web/` o `data/` en `main`, o a mano.

Hay que activarlo una vez en el repositorio: **Settings → Pages → Build and deployment → Source: GitHub Actions**.

## Licencia
El código está bajo licencia MIT ([LICENSE](LICENSE)). La licencia **no** cubre los documentos de terceros usados como material de prueba en `scraper/tests/fixtures/`, que pertenecen a sus autores. La relación de municipios procede del INE.
