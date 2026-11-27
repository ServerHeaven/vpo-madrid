"""Pure merge of scraped sources and manual overrides (ARCHITECTURE.md §3.3).

No IO and no clock: everything comes in as arguments.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

Promo = dict[str, Any]
Validator = Callable[[Promo], list[str]]

# Same rule as overrides.schema.json: no array indices; id, fuente_id and meta are not editable.
_POINTER = re.compile(
    r"^/(nombre|operador|regimen|programa|modalidad|estado|ubicacion|viviendas_total|tipologias"
    r"|requisitos|fechas|enlaces)(/[a-z_][a-z0-9_]*)*$"
)
DERIVED_STATE_RULE = "DERIVADA-ESTADO-PLAZO"


@dataclass(frozen=True)
class Aviso:
    tipo: str  # id_duplicado | override_huerfano | override_desfasado | override_invalido
    promo_id: str
    detalle: str


@dataclass(frozen=True)
class MergeResult:
    promociones: list[Promo]
    avisos: list[Aviso]


def covers(ancestor: str, pointer: str) -> bool:
    return pointer == ancestor or pointer.startswith(ancestor + "/")


def _principal_sha256(promo: Promo) -> str | None:
    return next((doc["sha256"] for doc in promo["enlaces"]["bases"] if doc["es_principal"]), None)


def _principal_url(promo: Promo) -> str | None:
    return next((doc["url"] for doc in promo["enlaces"]["bases"] if doc["es_principal"]), None)


def _set_pointer(promo: Promo, pointer: str, value: Any) -> None:
    *parents, leaf = pointer[1:].split("/")
    node: Any = promo
    for part in parents:
        node = node.get(part) if isinstance(node, dict) else None
    if not isinstance(node, dict) or leaf not in node:
        raise KeyError("la ruta no existe (si el objeto padre es null, corrige el objeto entero)")
    node[leaf] = value


def _touch(meta: dict[str, Any], day: str) -> None:
    meta["ultima_modificacion"] = max(meta["ultima_modificacion"], day)


def _apply_override(
    promo: Promo, campos: dict[str, Any], validate: Validator, avisos: list[Aviso]
) -> Promo:
    promo_id = promo["id"]
    current_sha = _principal_sha256(promo)  # taken before any correction touches /enlaces
    stale: list[str] = []

    # Parents first, so a more specific correction wins over a whole-object one.
    for pointer in sorted(campos, key=lambda p: (p.count("/"), p)):
        field = campos[pointer]
        if not _POINTER.match(pointer):
            avisos.append(Aviso("override_invalido", promo_id, f"{pointer}: ruta no permitida"))
            continue
        candidate = copy.deepcopy(promo)
        try:
            _set_pointer(candidate, pointer, copy.deepcopy(field["valor"]))
        except KeyError as error:
            avisos.append(Aviso("override_invalido", promo_id, f"{pointer}: {error.args[0]}"))
            continue
        errors = validate(candidate)
        if errors:
            avisos.append(Aviso("override_invalido", promo_id, f"{pointer}: {errors[0]}"))
            continue
        promo = candidate

        meta = promo["meta"]
        meta["procedencia"] = {k: v for k, v in meta["procedencia"].items() if not covers(pointer, k)}
        meta["procedencia"][pointer] = {
            "metodo": "override",
            "confianza": 1,
            "documento": _principal_url(promo),
            "pagina": None,
            "evidencia": field["motivo"][:400],
            "regla": None,
        }
        meta["campos_pendientes"] = [p for p in meta["campos_pendientes"] if not covers(pointer, p)]
        meta["campos_override"] = sorted({*meta["campos_override"], pointer})
        _touch(meta, field["fecha"])

        if field["fuente_sha256"] is not None and field["fuente_sha256"] != current_sha:
            stale.append(pointer)

    if stale:
        detail = f"la fuente cambió desde la corrección de: {', '.join(stale)}"
        avisos.append(Aviso("override_desfasado", promo_id, detail))
    return promo


def _derive_state(promo: Promo, today: date) -> None:
    deadline = promo["fechas"]["inscripcion_fin"]
    if promo["estado"] != "inscripcion_abierta" or deadline is None:
        return
    if "/estado" in promo["meta"]["campos_override"] or date.fromisoformat(deadline) >= today:
        return
    promo["estado"] = "inscripcion_cerrada"
    promo["meta"]["procedencia"]["/estado"] = {
        "metodo": "html",
        "confianza": 1,
        "documento": promo["enlaces"]["oficial"],
        "pagina": None,
        "evidencia": f"El plazo de inscripción terminó el {deadline}",
        "regla": DERIVED_STATE_RULE,
    }
    # Derived from the deadline, not from today, so later runs produce no diff.
    _touch(promo["meta"], (date.fromisoformat(deadline) + timedelta(days=1)).isoformat())


def merge(
    scraped: Iterable[Promo],
    overrides: dict[str, Any],
    *,
    today: date,
    validate: Validator,
) -> MergeResult:
    """Return the final promotion list. Inputs are never mutated.

    ``scraped`` is the concatenation of every source; manual entries take precedence over it.
    """
    avisos: list[Aviso] = []
    base: dict[str, Promo] = {}
    for promo in [*overrides["promociones_manuales"], *scraped]:
        if promo["id"] in base:
            kept = base[promo["id"]]["fuente_id"]
            detail = f"repetida en '{promo['fuente_id']}'; se conserva la de '{kept}'"
            avisos.append(Aviso("id_duplicado", promo["id"], detail))
            continue
        base[promo["id"]] = copy.deepcopy(promo)

    corrections = overrides["overrides"]
    for orphan in sorted(corrections.keys() - base.keys()):
        avisos.append(Aviso("override_huerfano", orphan, "no existe ninguna promoción con este id"))

    result: list[Promo] = []
    for promo_id in sorted(base):
        promo = base[promo_id]
        override = corrections.get(promo_id)
        if override is not None:
            promo = _apply_override(promo, override["campos"], validate, avisos)
        _derive_state(promo, today)
        if override is None or not override["ocultar"]:
            result.append(promo)
    return MergeResult(result, avisos)
