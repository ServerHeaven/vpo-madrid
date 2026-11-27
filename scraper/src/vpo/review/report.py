"""data/review-report.json: what needs a human, and why (ARCHITECTURE.md §3.2, §3.3 and §4.1).

The report is rebuilt on every run and never committed. This module must not import
``core.merge``, which imports it.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

from ..core.jsonio import write_json
from ..core.normalize import Municipios
from ..extraction import cache
from ..extraction.base import (
    CAMPOS_ACUMULATIVOS,
    Descarte,
    ExtractionContext,
    ExtractionResult,
    FieldResult,
)

Promo = dict[str, Any]

# Key fields (§3.2). "/fechas/inscripcion_fin" only counts while the registration is open.
CAMPOS_CLAVE = (
    "/estado",
    "/ubicacion/municipio_ine",
    "/tipologias",
    "/requisitos/ingresos_max_iprem",
    "/requisitos/empadronamiento",
    "/fechas/inscripcion_fin",
)
# Reasons that make any other field pending while it stays null (principle 3).
MOTIVOS_DE_REVISION = ("conflicto", "fuera_de_rango")
# Report-only reason: there is no cached extraction to explain the null.
NO_DISPONIBLE = "no_disponible"

_PSEUDO = "/tipologias/*"
_POINTERS = re.compile(r"/[a-z_][a-z0-9_]*(?:/[a-z_][a-z0-9_]*)*")


def _covers(ancestor: str, pointer: str) -> bool:
    return pointer == ancestor or pointer.startswith(ancestor + "/")


def sin_resolver(promo: Promo, pointer: str) -> bool:
    """Is this field still unknown? A requirement declared as not demanded is resolved."""
    if pointer.startswith(_PSEUDO):
        return False
    if pointer == "/estado":
        return promo["estado"] in (None, "desconocido")
    if pointer == "/tipologias":
        rows = promo["tipologias"]
        return not rows or any(row["renta_mensual_eur"] is None for row in rows)

    parts = pointer[1:].split("/")
    if parts[0] == "requisitos" and len(parts) > 1:
        requisitos = promo["requisitos"]
        if parts[1] in requisitos.get("no_exigidos", []):
            return False
        # The table by household size prevails over the flat limits.
        if parts[1] in ("ingresos_min_iprem", "ingresos_max_iprem") and requisitos["ingresos_por_miembros"]:
            return False
        # "Empadronado" without the years is still pending (§5.3).
        if parts[1:] == ["empadronamiento"]:
            registration = requisitos["empadronamiento"]
            return registration is None or registration["anios_min"] is None

    node: Any = promo
    for part in parts:
        if node is None:
            return True
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return node is None


def _overridden(promo: Promo, pointer: str) -> bool:
    return any(_covers(done, pointer) for done in promo["meta"]["campos_override"])


def campos_pendientes(promo: Promo, descartes: Iterable[Descarte] = ()) -> list[str]:
    """Sorted JSON pointers that need review; [] if the promotion has no bases document."""
    if not promo["enlaces"]["bases"]:
        return []
    pending = {
        pointer
        for pointer in CAMPOS_CLAVE
        if (pointer != "/fechas/inscripcion_fin" or promo["estado"] == "inscripcion_abierta")
        and sin_resolver(promo, pointer)
    }
    pending.update(
        item.campo
        for item in descartes
        if item.motivo in MOTIVOS_DE_REVISION
        and item.campo not in CAMPOS_ACUMULATIVOS
        and sin_resolver(promo, item.campo)
    )
    # A corrected field leaves the list even if the correction says "unknown" (§3.3 rule 7).
    return sorted(pointer for pointer in pending if not _overridden(promo, pointer))


def _principal(promo: Promo) -> dict[str, Any] | None:
    return next((doc for doc in promo["enlaces"]["bases"] if doc["es_principal"]), None)


def _candidate(item: FieldResult) -> dict[str, Any]:
    return {
        "valor": item.valor,
        "confianza": item.confianza,
        "pagina": item.pagina,
        "evidencia": item.evidencia,
        "regla": item.regla,
        "metodo": item.metodo,
        "documento": item.documento,
    }


def _review(
    promo: Promo,
    *,
    cache_dir: Path,
    municipios: Municipios,
    today: date,
    version: str,
    resolver: Callable[..., ExtractionResult] | None,
) -> dict[str, Any] | None:
    """The review entry of one promotion, or None if nothing is pending."""
    documents = promo["enlaces"]["bases"]
    if not documents:
        return None
    ine = promo["ubicacion"]["municipio_ine"]
    main = _principal(promo) or documents[0]

    entries: dict[str, cache.CacheEntry] = {}
    found: list[FieldResult] = []
    warnings: list[str] = []
    for document in documents:
        entry = cache.load(cache_dir, document["sha256"], ine, version)
        if entry is None:
            continue
        entries[document["sha256"]] = entry
        found += [c if c.documento else replace(c, documento=document["url"]) for c in entry.candidatos]
        warnings += entry.advertencias

    result = ExtractionResult()
    if entries:
        if resolver is None:
            from ..extraction.pipeline import resolver  # lazy: only needed with cached candidates
        context = ExtractionContext(
            fuente_id=promo["fuente_id"],
            fecha_ref=today,
            municipios=municipios,
            municipio_ine=ine,
            programa_hint=promo["programa"],
        )
        scanned = all(entry.necesita_ocr for entry in entries.values())
        result = resolver(found, context, necesita_ocr=scanned, advertencias=tuple(warnings))

    # meta (what the web shows) also carries what only an earlier extraction could tell us.
    pending = set(campos_pendientes(promo, result.descartes))
    pending.update(
        pointer
        for pointer in promo["meta"]["campos_pendientes"]
        if sin_resolver(promo, pointer) and not _overridden(promo, pointer)
    )
    if not pending:
        return None

    main_entry = entries.get(main["sha256"])
    fields = []
    for pointer in sorted(pending):
        discarded = [item for item in result.descartes if item.campo == pointer]
        # The most informative reason first.
        discarded.sort(key=lambda item: item.motivo not in MOTIVOS_DE_REVISION)
        first = discarded[0] if discarded else None
        if first is not None and first.motivo in MOTIVOS_DE_REVISION:
            reason = first.motivo
        elif main_entry is not None and main_entry.necesita_ocr:
            reason = "pdf_escaneado"
        elif main_entry is None:
            reason = NO_DISPONIBLE
        else:
            reason = first.motivo if first else "no_encontrado"
        seen = (first.candidatos if first else ()) or [c for c in found if c.campo == pointer]
        candidates = [_candidate(c if c.documento else replace(c, documento=main["url"])) for c in seen]
        fields.append({"campo": pointer, "motivo": reason, "candidatos": candidates})

    principal = _principal(promo)
    return {
        "promo_id": promo["id"],
        "nombre": promo["nombre"],
        "operador": promo["operador"]["nombre"],
        "municipio": promo["ubicacion"]["municipio"],
        "url_oficial": promo["enlaces"]["oficial"],
        "bases": [{k: d[k] for k in ("url", "titulo", "sha256", "es_principal")} for d in documents],
        "fuente_sha256": principal["sha256"] if principal else None,
        "detalle_completo": all(d["sha256"] in entries for d in documents),
        "no_exigidos": list(promo["requisitos"].get("no_exigidos", [])),
        "advertencias": sorted(set(warnings)),
        "campos": fields,
    }


def _stale(aviso: Any, promo: Promo | None, overrides: dict[str, Any] | None) -> dict[str, Any]:
    # merge.Aviso only carries text: "...: /a, /b".
    pointers = sorted(set(_POINTERS.findall(aviso.detalle.partition(":")[2])))
    corrections = ((overrides or {}).get("overrides", {}).get(aviso.promo_id) or {}).get("campos", {})
    principal = _principal(promo) if promo else None
    return {
        "promo_id": aviso.promo_id,
        "nombre": promo["nombre"] if promo else aviso.promo_id,
        "url_oficial": promo["enlaces"]["oficial"] if promo else None,
        "url_bases": principal["url"] if principal else None,
        "sha256_actual": principal["sha256"] if principal else None,
        "campos": [
            {"campo": p, "sha256_anterior": corrections.get(p, {}).get("fuente_sha256")} for p in pointers
        ],
    }


def construir_informe(
    promociones: Iterable[Promo],
    avisos: Iterable[Any],
    *,
    cache_dir: Path,
    municipios: Municipios,
    today: date,
    version: str,
    overrides: dict[str, Any] | None = None,
    resolver: Callable[..., ExtractionResult] | None = None,
) -> dict[str, Any]:
    """JSON-serialisable report of the final (merged) promotion list.

    ``avisos`` are core.merge.Aviso objects. ``overrides`` (the content of overrides.json) is
    only needed to quote the old hash of a stale correction. ``resolver`` defaults to
    extraction.pipeline.resolver.
    """
    promos = sorted(promociones, key=lambda p: p["id"])
    by_id = {promo["id"]: promo for promo in promos}
    notices = list(avisos)
    reviews = [
        _review(
            promo,
            cache_dir=cache_dir,
            municipios=municipios,
            today=today,
            version=version,
            resolver=resolver,
        )
        for promo in promos
    ]
    return {
        "schema_version": 1,
        "fecha": today.isoformat(),
        "extractor_version": version,
        "publicadas": sorted(by_id),
        "revisiones": [entry for entry in reviews if entry is not None],
        "overrides_desfasados": [
            _stale(aviso, by_id.get(aviso.promo_id), overrides)
            for aviso in sorted(notices, key=lambda a: a.promo_id)
            if aviso.tipo == "override_desfasado"
        ],
        "avisos": [{"tipo": a.tipo, "promo_id": a.promo_id, "detalle": a.detalle} for a in notices],
    }


def escribir_informe(path: Path, informe: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, informe)
