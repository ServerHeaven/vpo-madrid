"""Source id (data/fuentes.json) -> adapter class."""

from __future__ import annotations

from typing import Any

from ..core.normalize import Municipios
from .base import SourceAdapter
from .emsv_getafe import EmsvGetafeAdapter
from .emv_alcobendas import EmvAlcobendasAdapter
from .emvs_madrid import EmvsMadridAdapter
from .plan_vive_cam import PlanViveCamAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {
    adapter.id: adapter
    for adapter in (EmvsMadridAdapter, PlanViveCamAdapter, EmsvGetafeAdapter, EmvAlcobendasAdapter)
}


def build_adapter(config: dict[str, Any], municipios: Municipios) -> SourceAdapter:
    try:
        adapter = ADAPTERS[config["id"]]
    except KeyError:
        raise LookupError(f"no hay adaptador para la fuente '{config['id']}'") from None
    return adapter(config, municipios)
