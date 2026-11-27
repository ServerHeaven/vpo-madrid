# vpo-madrid

Buscador de promociones de alquiler protegido (VPPB, VPPL, Plan Vive, promociones municipales) en la Comunidad de Madrid.

**Estado:** en construcción. Se leen las páginas HTML de EMVS Madrid y del Plan Vive y se extraen requisitos y rentas de las bases en PDF. La web (buscador y fichas) está en [web/](web/) y se publicará en <https://serverheaven.github.io/vpo-madrid/> cuando se active GitHub Pages. Todavía no hay actualización diaria automática ni calculadora.

La información es orientativa. No tenemos relación con las administraciones ni con las operadoras: la convocatoria oficial prevalece siempre.

## Cómo funciona
Los datos son ficheros JSON en [data/](data/). GitHub Actions publica con ellos una web estática; más adelante, un proceso diario los actualizará. No hay servidores, bases de datos ni datos personales de visitantes. El diseño completo está en [ARCHITECTURE.md](ARCHITECTURE.md).

## Corregir un dato
Edita [data/overrides.json](data/overrides.json). Las correcciones ganan siempre al scraper, y al llegar a `main` la web se vuelve a publicar con ellas:

```json
"overrides": {
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
}
```

- `fuente_sha256`: el hash del PDF que revisaste, o `null` si no hay PDF. Si el PDF cambia, se avisa.
- Las listas (`/tipologias`, `/enlaces/bases`) se sustituyen enteras.
- Si el objeto padre es `null` (por ejemplo `empadronamiento`), corrige el objeto completo.
- Un requisito en `null` significa «no lo sabemos». Si consta que **no se exige**, déjalo en `null` y añádelo a `/requisitos/no_exigidos` (la lista se sustituye entera), por ejemplo `["empadronamiento"]`.

Los datos que no se han podido extraer de las bases con seguridad se publican como issues con la etiqueta `needs-review`, cada uno con el bloque listo para pegar aquí.

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

## Publicación
[deploy.yml](.github/workflows/deploy.yml) aplica las correcciones (`vpo merge`, sin hacer commit), construye la web y la publica en <https://serverheaven.github.io/vpo-madrid/>. Se ejecuta al cambiar `web/` o `data/` en `main`, o a mano.

Hay que activarlo una vez en el repositorio: **Settings → Pages → Build and deployment → Source: GitHub Actions**.

## Licencia
El código está bajo licencia MIT ([LICENSE](LICENSE)). La licencia **no** cubre los documentos de terceros usados como material de prueba en `scraper/tests/fixtures/`, que pertenecen a sus autores. La relación de municipios procede del INE.
