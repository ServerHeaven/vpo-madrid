# CLAUDE.md

Agregador estático de alquiler protegido en la Comunidad de Madrid. El diseño está en [ARCHITECTURE.md](ARCHITECTURE.md): léelo antes de empezar una fase y no implementes nada fuera de su alcance.

## Configuración del proyecto
- Repositorio: `vpo-madrid`. Usuario de GitHub: `tu-usuario` (marcador de posición: confirmar antes de publicar).
- Sitio: GitHub Pages sin dominio propio, `site = https://tu-usuario.github.io`, `base = /vpo-madrid/`.
- User-Agent del scraper: `vpo-madrid-bot/1.0 (+https://tu-usuario.github.io/vpo-madrid/metodologia)`. Sin datos personales.
- Web: Astro + Preact. Calculadora: base imponible IRPF como dato principal; el bruto es una estimación orientativa y marcada.
- Primeras fuentes: EMVS Madrid y Plan Vive.

## Comandos (desde `scraper/`)
```
uv sync
uv run python -m pytest
uv run python -m vpo merge
uv run python -m vpo validate
```
Usa `python -m pytest`, no `pytest`: Windows puede bloquear el lanzador `.exe`.

## Reglas
- **`null` antes que adivinar.** Ante duda, conflicto o valor fuera de rango, `null`.
- **El código nunca escribe en los archivos manuales:** `data/overrides.json`, `iprem.json`, `programas.json`, `fuentes.json`, `municipios.json`. Solo escribe `promociones.json`, `state.json` y `sources/*.json`.
- El JSON Schema de `data/schema/` es la fuente de verdad. Si cambias uno, cambia `core/models.py` en el mismo commit.
- Todas las claves son obligatorias; lo desconocido es `null`.
- Idioma de dominio en español (nombres de campos, datos, mensajes). Código y comentarios técnicos en inglés.
- Un valor `verificado: true` exige una fuente oficial citada. Registro en [docs/verificaciones.md](docs/verificaciones.md).
- Si el diseño no encaja con la realidad, escribe un ADR en `docs/decisiones/` y pregunta antes de desviarte.

## Fixtures reales
Se versionan en `scraper/tests/fixtures/{html,pdf}/`. **Nunca** incluyas documentos con datos personales: listados de solicitantes, admitidos, excluidos o adjudicatarios, ni documentos con nombres o DNI de particulares. Revisa cada fichero antes de añadirlo; una vez publicado en Git no se borra del historial.
Cada fixture anota su URL de origen y fecha de descarga en `scraper/tests/fixtures/FUENTES.md`.
