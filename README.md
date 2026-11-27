# vpo-madrid

Buscador de promociones de alquiler protegido (VPPB, VPPL, Plan Vive, promociones municipales) en la Comunidad de Madrid.

**Estado:** en construcción. Se leen las páginas HTML de EMVS Madrid y del Plan Vive y se extraen requisitos y rentas de las bases en PDF. Todavía no hay web.

La información es orientativa. No tenemos relación con las administraciones ni con las operadoras: la convocatoria oficial prevalece siempre.

## Cómo funciona
Los datos son ficheros JSON en [data/](data/). Un proceso diario en GitHub Actions los actualizará y publicará una web estática. No hay servidores, bases de datos ni datos personales de visitantes. El diseño completo está en [ARCHITECTURE.md](ARCHITECTURE.md).

## Corregir un dato
Edita [data/overrides.json](data/overrides.json). Las correcciones ganan siempre al scraper:

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

## Licencia
El código está bajo licencia MIT ([LICENSE](LICENSE)). La licencia **no** cubre los documentos de terceros usados como material de prueba en `scraper/tests/fixtures/`, que pertenecen a sus autores. La relación de municipios procede del INE.
