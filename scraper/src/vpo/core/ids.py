"""Stable promotion ids: {operador}-{municipio}-{nombre}, frozen per ficha URL."""

from __future__ import annotations

from .normalize import slugify
from .state import State

_MAX_LENGTH = 120  # data/schema/promocion.schema.json#/$defs/slug


def _truncate(slug: str, length: int) -> str:
    return slug[:length].rstrip("-")


def build_slug(operador_id: str, municipio: str, nombre: str) -> str:
    """At most 120 characters, matching the schema's slug pattern."""
    # Empty parts are skipped so the result never has doubled hyphens.
    slug = "-".join(filter(None, map(slugify, (operador_id, municipio, nombre))))
    if not slug:
        raise ValueError("no se puede generar un id: operador, municipio y nombre están vacíos")
    return _truncate(slug, _MAX_LENGTH)


def get_or_create_id(state: State, *, url: str, operador_id: str, municipio: str, nombre: str) -> str:
    """Return the id frozen in state['promo_ids'][url], creating it (collision-free) if missing.

    ``url`` is used verbatim as the key: fragments tell apart promotions sharing a page.
    """
    frozen = state["promo_ids"]
    if url in frozen:
        return frozen[url]

    base = build_slug(operador_id, municipio, nombre)
    taken = set(frozen.values())
    candidate, number = base, 1
    while candidate in taken:
        number += 1
        suffix = f"-{number}"
        candidate = _truncate(base, _MAX_LENGTH - len(suffix)) + suffix
    frozen[url] = candidate
    return candidate
