"""Pure construction of ``meta``, and handling of promotions that left their source."""

from __future__ import annotations

import copy
from datetime import date
from typing import Any

from ..sources.base import Parsed

Promo = dict[str, Any]
MISSING_DAYS_TO_FINISH = 30
MISSING_STATE_RULE = "DERIVADA-DESAPARECIDA"

# Order of "required" in data/schema/promocion.schema.json, without "id" and "meta".
_DATA_KEYS = (
    "nombre",
    "operador",
    "fuente_id",
    "regimen",
    "programa",
    "modalidad",
    "estado",
    "ubicacion",
    "viviendas_total",
    "tipologias",
    "requisitos",
    "fechas",
    "enlaces",
)


def build_promo(
    parsed: Parsed, *, promo_id: str, previous: Promo | None, today: date, extractor_version: str
) -> Promo:
    """A promotion present in its source. Unchanged data keeps ``ultima_modificacion``."""
    wrong = set(parsed.datos) ^ set(_DATA_KEYS)
    if wrong:
        raise ValueError(f"{promo_id}: claves que faltan o sobran en los datos: {', '.join(sorted(wrong))}")

    datos = {key: copy.deepcopy(parsed.datos[key]) for key in _DATA_KEYS}
    procedencia = copy.deepcopy(parsed.procedencia)
    first_seen = modified = today.isoformat()
    if previous is not None:
        meta = previous["meta"]
        first_seen = meta["primera_deteccion"]
        unchanged = (
            meta["activa_en_fuente"]
            and meta["procedencia"] == procedencia
            and all(previous[key] == datos[key] for key in _DATA_KEYS)
        )
        if unchanged:
            modified = meta["ultima_modificacion"]

    return {
        "id": promo_id,
        **datos,
        "meta": {
            "primera_deteccion": first_seen,
            "ultima_modificacion": modified,
            "activa_en_fuente": True,
            "campos_pendientes": [],  # pending-field review arrives in Phase 3
            "campos_override": [],  # overrides are applied by merge
            "procedencia": procedencia,
            "extractor_version": extractor_version,
        },
    }


def mark_missing(previous: Promo, *, today: date) -> Promo:
    """A promotion no longer listed: keep its data, set activa_en_fuente = False.

    30 days after that, estado becomes 'finalizada'. Never deletes. Does not mutate ``previous``.
    """
    promo = copy.deepcopy(previous)
    meta = promo["meta"]
    if meta["activa_en_fuente"]:
        meta["activa_en_fuente"] = False
        meta["ultima_modificacion"] = today.isoformat()  # records when it vanished
        return promo

    # While inactive, ultima_modificacion is the day it vanished.
    vanished = date.fromisoformat(meta["ultima_modificacion"])
    if promo["estado"] == "finalizada" or (today - vanished).days < MISSING_DAYS_TO_FINISH:
        return promo

    promo["estado"] = "finalizada"
    meta["ultima_modificacion"] = today.isoformat()
    meta["procedencia"]["/estado"] = {
        "metodo": "html",
        "confianza": 1,
        "documento": promo["enlaces"]["oficial"],
        "pagina": None,
        "evidencia": (
            f"No aparece en su fuente desde el {vanished.isoformat()} "
            f"({MISSING_DAYS_TO_FINISH} días o más)"
        ),
        "regla": MISSING_STATE_RULE,
    }
    return promo
