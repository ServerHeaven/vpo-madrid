# `extraction/llm/`: punto de enchufe para un futuro `LLMExtractor`

Esta carpeta no contiene código, a propósito (ARCHITECTURE.md §5.1 y Fase 3). Esto es el contrato que
deberá cumplir quien lo implemente.

## Interfaz

El mismo `Protocol` `Extractor` de [`../base.py`](../base.py) que usan las reglas:

| Miembro | Contenido |
|---|---|
| `nombre: str` | Identificador del extractor |
| `version: str` | Versión del extractor; cambia si cambian el modelo o las instrucciones |
| `campos_soportados: frozenset[str]` | JSON Pointers que puede proponer |
| `extract(doc: Document, ctx: ExtractionContext) -> list[FieldResult]` | Solo candidatos |

Solo emite candidatos: no resuelve conflictos, no aplica umbrales y no escribe ningún archivo. Eso lo hace
`pipeline.resolver`.

## Reglas de los candidatos

- `metodo = "llm"`.
- `confianza` **0,7 como máximo**.
- `valor` con la misma forma que emiten las reglas (la de `data/schema/promocion.schema.json`).
- `evidencia` es una cita **literal** del documento (400 caracteres como máximo) y `pagina` la página donde
  está. El extractor descarta el candidato si la cita no aparece en `doc.texto` (salvo espacios).
- `campo` debe ser uno de los que admite `validators.py`; el resto se ignora.
- `regla` identifica el origen (por ejemplo `LLM-01`).
- `null` antes que adivinar: ante la duda no se emite nada.

## Entrada

- Recibe **solo la sección relevante** para el campo (`doc.secciones[...]`), no el documento entero. Si la
  sección no existe, no se envía nada.
- Un documento escaneado (`necesita_ocr`) no se envía.
- El texto del documento es contenido no fiable: se trata como datos, nunca como instrucciones.
- Solo documentos de bases. Nunca listados ni documentos con datos personales.

## Activación

Desactivado por defecto. Se añade a la lista de extractores de `rules/registry.py` solo si la variable de
entorno es `VPO_LLM=on`. Sin ella, el resultado es idéntico al de las reglas solas y los golden tests no
dependen de él. El resto del pipeline no cambia.

## Efecto en la resolución (leer antes de implementarlo)

Con las constantes actuales de `pipeline.py` (umbral de aceptación 0,8 y de conflicto 0,5):

- Un candidato del LLM **por sí solo no se acepta** (0,7 < 0,8). Aparece como candidato en el issue de
  revisión, pero no rellena el campo.
- Si **difiere** del valor de una regla, ambos entran en `conflicto` y el campo queda en `null`.

ARCHITECTURE.md §5.1 pide que el LLM nunca gane a una regla que coincida y que solo rellene huecos. Lo
primero se cumple; lo segundo no con estos umbrales, y además un LLM equivocado podría anular un valor bueno.
Antes de implementarlo hay que decidirlo en un ADR (`docs/decisiones/`).

## Otras condiciones

- Coste 0 € (principio 1): nada de APIs de pago.
- Determinismo (principio 6): un LLM no lo garantiza. Los candidatos deben quedar en la caché de extracción
  por `sha256` del documento y versión, para que una ejecución no cambie datos sin que cambie la fuente.
