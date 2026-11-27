"""Bases PDFs of a promotion: download, extract (or reuse), resolve and merge with the HTML data.

Used by the orchestrator. Writes only inside the cache folder; state.json is updated by the
caller once the whole source has succeeded.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from . import __version__
from .core.hashing import sha256_bytes, sha256_text
from .core.normalize import Municipios
from .core.state import canonical_url, document_key
from .extraction import cache, pipeline
from .extraction.base import Descarte, ExtractionContext, FieldResult
from .extraction.documents.pdf import DocumentoIlegible, leer_pdf
from .extraction.fusion import aplicar
from .extraction.preprocess import preparar
from .sources.base import DocumentoRef, Fetcher, FetchError, Parsed

Promo = dict[str, Any]


@dataclass(frozen=True)
class DocumentoLeido:
    """What state.json needs to know about one downloaded PDF."""

    url: str
    etag: str | None
    last_modified: str | None
    sha256_bytes: str
    sha256_texto: str
    ocr_necesario: bool
    extractor_version: str


@dataclass(frozen=True)
class Bases:
    parsed: Parsed  # HTML data enriched with what the PDFs say
    descartes: tuple[Descarte, ...] = ()
    documentos: tuple[DocumentoLeido, ...] = ()
    avisos: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class _Extraction:
    entry: cache.CacheEntry
    sha256: str


def pdf_path(cache_dir: Path, url: str) -> Path:
    return cache_dir / "pdf" / f"{document_key(url)}.pdf"


def _previous_bases(previous: Promo | None) -> dict[str, dict[str, Any]]:
    if previous is None:
        return {}
    return {canonical_url(doc["url"]): doc for doc in previous["enlaces"]["bases"]}


def _extract(
    content: bytes,
    url: str,
    context: ExtractionContext,
    *,
    cache_dir: Path,
    known: dict[str, Any] | None,  # state["documentos"] entry of this URL, if any
    force: bool,
) -> _Extraction:
    """Candidates of one document, extracting only when needed (ARCHITECTURE.md §3.4)."""
    sha = sha256_bytes(content)
    ine = context.municipio_ine
    if not force and (entry := cache.load(cache_dir, sha, ine, __version__)):
        return _Extraction(entry, sha)

    document = leer_pdf(content, url=url)
    # A scan has no text to compare: only its bytes tell whether it changed.
    text = "" if document.necesita_ocr else "\n".join(page.texto for page in document.paginas)
    sha_text = sha256_text(text) if text else sha

    entry = None
    if not force and known and known["sha256_texto"] == sha_text and known["sha256_bytes"]:
        # Same text in a regenerated file: not extracted again.
        entry = cache.load(cache_dir, known["sha256_bytes"], ine, __version__)
    if entry is None:
        candidates: list[FieldResult] = []
        warnings: list[str] = []
        if not document.necesita_ocr:
            candidates, warnings = pipeline.extraer_candidatos(preparar(document), context)
        entry = cache.CacheEntry(
            extractor_version=__version__,
            sha256_texto=sha_text,
            municipio_ine=ine,
            necesita_ocr=document.necesita_ocr,
            candidatos=tuple(candidates),
            advertencias=tuple(warnings),
        )
    cache.store(cache_dir, sha, entry)
    return _Extraction(entry, sha)


def procesar_bases(
    parsed: Parsed,
    refs: list[DocumentoRef],
    http: Fetcher,
    *,
    previous: Promo | None,
    known_documents: dict[str, Any],  # state["documentos"]
    municipios: Municipios,
    today: date,
    cache_dir: Path,
    force: bool = False,
) -> Bases:
    """Enrich ``parsed`` with the linked bases.

    A document that was already part of the promotion and cannot be read raises, so the caller
    keeps the previous data. A new one that cannot be read is only a warning.
    """
    if not refs:
        return Bases(parsed)

    before = _previous_bases(previous)
    datos = parsed.datos
    ine = datos["ubicacion"]["municipio_ine"]
    links: list[dict[str, Any]] = []
    read: list[DocumentoLeido] = []
    extractions: list[_Extraction] = []
    warnings: list[str] = []
    context: ExtractionContext | None = None

    for ref in refs:
        url = canonical_url(ref.url)
        old = before.get(url)
        first_seen = old["detectado_en"] if old else today.isoformat()
        # Dates are judged against the day the document appeared, so results do not drift.
        context = ExtractionContext(
            fuente_id=datos["fuente_id"],
            fecha_ref=date.fromisoformat(first_seen),
            municipios=municipios,
            municipio_ine=ine,
            programa_hint=datos["programa"],
            promo_parcial=copy.deepcopy(datos),
        )
        try:
            response = http.get(ref.url)
            extraction = _extract(
                response.content,
                url,
                context,
                cache_dir=cache_dir,
                known=known_documents.get(document_key(url)),
                force=force,
            )
        except (FetchError, DocumentoIlegible) as error:
            if old:
                raise
            warnings.append(f"aviso: no se pudo leer {ref.url}: {error}")
            continue

        target = pdf_path(cache_dir, url)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)

        links.append(
            {
                "url": url,
                "titulo": ref.titulo,
                "sha256": extraction.sha256,
                "detectado_en": first_seen,
                "es_principal": ref.es_principal,
            }
        )
        read.append(
            DocumentoLeido(
                url=url,
                etag=response.etag,
                last_modified=response.last_modified,
                sha256_bytes=extraction.sha256,
                sha256_texto=extraction.entry.sha256_texto,
                ocr_necesario=extraction.entry.necesita_ocr,
                extractor_version=extraction.entry.extractor_version,
            )
        )
        extractions.append(extraction)
        warnings += [f"aviso: {url}: {text}" for text in extraction.entry.advertencias]

    if not links:
        return Bases(parsed, avisos=tuple(warnings))

    result = pipeline.resolver(
        [candidate for extraction in extractions for candidate in extraction.entry.candidatos],
        context,
        necesita_ocr=all(extraction.entry.necesita_ocr for extraction in extractions),
    )
    merged, procedencia, descartes = aplicar(datos, parsed.procedencia, result)
    merged["enlaces"] = {**merged["enlaces"], "bases": links}
    return Bases(
        parsed=Parsed(merged, procedencia),
        # What the resolution rejected plus what could not be merged with the HTML data.
        descartes=(*result.descartes, *descartes),
        documentos=tuple(read),
        avisos=tuple(warnings),
    )
