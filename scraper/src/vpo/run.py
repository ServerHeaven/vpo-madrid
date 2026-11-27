"""Orchestrator of `vpo run`, with per-source and per-ficha fault isolation (ARCHITECTURE.md §4.1).

Writes only state.json and sources/<id>.json. Problems with those files or with the schemas are
global and propagate; anything that goes wrong while reading a source stays inside that source.
"""

from __future__ import annotations

import copy
import time
from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .core.hashing import SelectorNotFound, sha256_bytes, sha256_fragment
from .core.http import HttpClient
from .core.ids import get_or_create_id
from .core.jsonio import read_json, write_json
from .core.lifecycle import build_promo, mark_missing
from .core.normalize import Municipios
from .core.state import (
    State,
    canonical_url,
    load_state,
    record_html_document,
    record_source_run,
    save_state,
)
from .core.validate import schema_errors
from .sources.base import DeadlineExceeded, Fetcher, Ficha, ListingError, Response, SourceAdapter
from .sources.registry import build_adapter

AdapterFactory = Callable[[dict[str, Any], Municipios], SourceAdapter]
HttpFactory = Callable[[dict[str, Any], float, Path], HttpClient]  # (source config, deadline, cache_dir)
Promo = dict[str, Any]

_MAX_ERROR_LENGTH = 500


class UnknownSourceError(ValueError):
    """A requested source does not exist or is not active."""


@dataclass
class SourceReport:
    fuente_id: str
    estado: str  # ok | degradado | error
    vistas: int | None = None
    cambios: int = 0
    errores: list[str] = field(default_factory=list)
    duracion_s: float = 0.0


@dataclass
class RunReport:
    fuentes: list[SourceReport] = field(default_factory=list)


@dataclass(frozen=True)
class _Context:
    """What every source shares."""

    schema_dir: Path
    cache_dir: Path
    municipios: Municipios
    codigos_ine: frozenset[str]
    today: date
    adapter_factory: AdapterFactory
    http_factory: HttpFactory
    clock: Callable[[], float]


def _describe(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"[:_MAX_ERROR_LENGTH]


def _load_checked(path: Path, schema: str, schema_dir: Path) -> Any:
    content = read_json(path)
    if errors := schema_errors(content, schema, schema_dir):
        raise ValueError(f"{path.name} no cumple el schema: " + "; ".join(errors[:5]))
    return content


def _select(sources: list[dict[str, Any]], only: set[str] | None) -> list[dict[str, Any]]:
    active = [source for source in sources if source["activa"]]
    if only is None:
        return active
    if unknown := sorted(only - {source["id"] for source in active}):
        raise UnknownSourceError(f"fuente desconocida o inactiva: {', '.join(unknown)}")
    return [source for source in active if source["id"] in only]


def _parse_ficha(
    adapter: SourceAdapter,
    ficha: Ficha,
    http: Fetcher,
    state: State,
    previous: dict[str, Promo],
    context: _Context,
    source_id: str,
) -> Promo:
    parsed = adapter.parsear_ficha(ficha, http)
    datos = parsed.datos
    # The id is frozen on a scratch copy, adopted only if the promotion turns out to be valid.
    trial = {**state, "promo_ids": dict(state["promo_ids"])}
    promo_id = get_or_create_id(
        trial,
        url=ficha.url,
        operador_id=datos["operador"]["id"],
        municipio=datos["ubicacion"]["municipio"],
        nombre=datos["nombre"],
    )
    promo = build_promo(
        parsed,
        promo_id=promo_id,
        previous=previous.get(promo_id),
        today=context.today,
        extractor_version=__version__,
    )
    if errors := schema_errors(promo, "promocion", context.schema_dir):
        raise ValueError(f"la promoción no cumple el schema: {errors[0]}")
    if promo["fuente_id"] != source_id:
        raise ValueError(f"fuente_id '{promo['fuente_id']}' no es '{source_id}'")
    if promo["ubicacion"]["municipio_ine"] not in context.codigos_ine:
        raise ValueError(f"municipio_ine inexistente: {promo['ubicacion']['municipio_ine']}")
    state["promo_ids"] = trial["promo_ids"]
    return promo


def _record_pages(
    state: State,
    log: list[Response],
    *,
    source_id: str,
    selector: str,
    links: list[tuple[str, str]],  # (page url, promo id)
    today: date,
) -> list[str]:
    """Record every page read in state['documentos']. Return warnings."""
    owners: defaultdict[str, set[str]] = defaultdict(set)
    for url, promo_id in links:
        owners[canonical_url(url)].add(promo_id)

    # Keyed by the requested URL: a redirect target may differ on every run.
    pages = {canonical_url(response.requested_url): response for response in log}
    warnings: list[str] = []
    for url, response in pages.items():
        try:
            sha256_texto = sha256_fragment(response.text, selector)
        except SelectorNotFound:
            sha256_texto = None
            warnings.append(f"aviso: el selector '{selector}' no encuentra nada en {url}")
        record_html_document(
            state,
            url=url,
            fuente_id=source_id,
            promo_ids=sorted(owners.get(url, set()) | owners.get(canonical_url(response.url), set())),
            etag=response.etag,
            last_modified=response.last_modified,
            sha256_bytes=sha256_bytes(response.content),
            sha256_texto=sha256_texto,
            today=today,
        )
    return warnings


def _scrape_source(
    source: dict[str, Any],
    report: SourceReport,
    state: State,  # a private copy: the caller adopts it only if this returns
    previous: dict[str, Promo],
    context: _Context,
) -> tuple[dict[str, Promo], str | None]:
    """Return the source's new promotions by id and its error summary. Raise if the source failed."""
    source_id = source["id"]
    deadline = context.clock() + source["timeout_s"]
    adapter = context.adapter_factory(source, context.municipios)
    http = context.http_factory(source, deadline, context.cache_dir)
    try:
        fichas = adapter.listar(http)
        if not fichas:
            raise ListingError("el listado no contiene ninguna promoción")
        if len({ficha.url for ficha in fichas}) != len(fichas):
            raise ListingError("el listado repite URLs de ficha")
        report.vistas = len(fichas)

        promos: dict[str, Promo] = {}
        listed: list[tuple[str, str]] = []  # (ficha url, promo id) of every promotion still published
        failures: list[str] = []
        for ficha in fichas:
            if context.clock() > deadline:
                raise DeadlineExceeded(f"superado el tiempo máximo de {source['timeout_s']} s")
            try:
                promo = _parse_ficha(adapter, ficha, http, state, previous, context, source_id)
            except DeadlineExceeded:
                raise
            except Exception as error:
                failures.append(f"{ficha.url}: {_describe(error)}")
                # Still published: keep what we had, and never treat it as disappeared.
                promo_id = state["promo_ids"].get(ficha.url)
                if promo_id not in previous:
                    continue
                promo = previous[promo_id]
            promos[promo["id"]] = promo
            listed.append((ficha.url, promo["id"]))

        report.errores = failures
        if len(failures) == len(fichas):
            raise RuntimeError(f"fallaron todas las fichas ({len(fichas)}); primera: {failures[0]}")

        for promo_id, promo in previous.items():
            if promo_id not in promos:
                promos[promo_id] = mark_missing(promo, today=context.today)

        links = listed + [(promo["enlaces"]["oficial"], promo_id) for promo_id, promo in promos.items()]
        warnings = _record_pages(
            state,
            http.log,
            source_id=source_id,
            selector=adapter.selector_hash(),
            links=links,
            today=context.today,
        )
        # Checked here so that bad page data fails this source instead of the final save.
        if errors := schema_errors(state, "state", context.schema_dir):
            raise ValueError(f"el estado resultante no cumple el schema: {errors[0]}")

        report.errores = failures + warnings
        report.estado = "degradado" if len(failures) * 2 > len(fichas) else "ok"
        summary = None
        if failures:
            summary = f"{len(failures)} de {len(fichas)} fichas con error; primera: {failures[0]}"
        return promos, summary
    finally:
        with suppress(Exception):
            http.close()


def run(
    data_dir: Path,
    *,
    today: date,
    now: datetime,
    only: set[str] | None = None,
    adapter_factory: AdapterFactory = build_adapter,
    http_factory: HttpFactory | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> RunReport:
    """Scrape the active sources into data/sources/ and data/state.json.

    A failing source is reported, not raised. UnknownSourceError if ``only`` names a source that is
    not active; other exceptions mean the data folder itself is broken.
    """
    schema_dir = data_dir / "schema"
    catalogue = _load_checked(data_dir / "fuentes.json", "fuentes", schema_dir)
    sources = _select(catalogue["fuentes"], only)
    report = RunReport()
    if not sources:
        return report

    def default_http_factory(config: dict[str, Any], deadline: float, cache_dir: Path) -> HttpClient:
        return HttpClient(
            min_interval_s=config["intervalo_s"], deadline=deadline, cache_dir=cache_dir, clock=clock
        )

    # Everything that can fail globally is loaded before any source is touched.
    context = _Context(
        schema_dir=schema_dir,
        cache_dir=data_dir.resolve().parent / ".cache" / "http",
        municipios=Municipios.load(data_dir),
        codigos_ine=frozenset(m["ine"] for m in read_json(data_dir / "municipios.json")["municipios"]),
        today=today,
        adapter_factory=adapter_factory,
        http_factory=http_factory or default_http_factory,
        clock=clock,
    )
    state_path = data_dir / "state.json"
    state = load_state(state_path)
    if errors := schema_errors(state, "state", schema_dir):
        raise ValueError("state.json no cumple el schema: " + "; ".join(errors[:5]))
    sources_dir = data_dir / "sources"
    old_files: dict[str, Any] = {}
    for source in sources:
        path = sources_dir / f"{source['id']}.json"
        old_files[source["id"]] = _load_checked(path, "source", schema_dir) if path.is_file() else None

    for source in sources:
        source_id = source["id"]
        old = old_files[source_id]
        previous = {promo["id"]: promo for promo in old["promociones"]} if old else {}
        source_report = SourceReport(source_id, "error")
        work = copy.deepcopy(state)
        content = None
        start = clock()
        try:
            promos, summary = _scrape_source(source, source_report, work, previous, context)
        except Exception as error:
            summary = _describe(error)
            source_report.errores.insert(0, summary)
        else:
            content = {
                "schema_version": 1,
                "fuente_id": source_id,
                "promociones": [promos[promo_id] for promo_id in sorted(promos)],
            }
            # Each promotion was already validated: a failure here is a bug, so it propagates.
            if errors := schema_errors(content, "source", schema_dir):
                raise ValueError(f"{source_id}.json no cumple el schema: " + "; ".join(errors[:5]))
            state = work
            source_report.cambios = sum(promo != previous.get(i) for i, promo in promos.items())
        source_report.duracion_s = round(max(clock() - start, 0.0), 1)

        record_source_run(
            state,
            source_id,
            estado=source_report.estado,
            now=now,
            promociones_vistas=None if source_report.estado == "error" else source_report.vistas,
            duracion_s=source_report.duracion_s,
            error=summary,
        )
        # State goes first: a source file must never hold an id that state.json does not know.
        save_state(state_path, state, schema_dir)
        if content is not None and content != old:
            sources_dir.mkdir(exist_ok=True)
            write_json(sources_dir / f"{source_id}.json", content)
        report.fuentes.append(source_report)
    return report
