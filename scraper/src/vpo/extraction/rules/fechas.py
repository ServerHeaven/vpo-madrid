"""Dates: REG-FECHA-01..04 (ARCHITECTURE.md §5.3).

A date is only emitted when its context says what it is. Relative terms ("20 dias desde...")
produce nothing (REG-FECHA-04). Plausibility against ``fecha_ref`` is the pipeline's job.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date

from ..base import Document, ExtractionContext, FieldResult
from ..patterns import fechas as p

INICIO = "/fechas/inscripcion_inicio"
FIN = "/fechas/inscripcion_fin"
SORTEO = "/fechas/sorteo"
ENTREGA = "/fechas/entrega_prevista"
BASE = 0.85


def _fecha(match: re.Match[str], prefix: str) -> date | None:
    if match[f"{prefix}y"]:
        day, month, year = match[f"{prefix}d"], p.MESES[match[f"{prefix}m"]], match[f"{prefix}y"]
    else:
        day, month, year = match[f"{prefix}nd"], match[f"{prefix}nm"], match[f"{prefix}ny"]
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def _regla_formato(match: re.Match[str], prefix: str) -> str:
    return "REG-FECHA-01" if match[f"{prefix}y"] else "REG-FECHA-02"


def _es_de_norma(text: str, position: int) -> bool:
    return bool(p.FECHA_NORMA.search(text[max(position - 100, 0) : position]))


def _es_plazo_de_inscripcion(text: str, position: int) -> bool:
    """The current sentence decides; if it says nothing, the previous 200 characters do."""
    window = text[max(position - p.VENTANA_CONTEXTO, 0) : position]
    sentence = re.split(r"\.\s", window)[-1]
    if p.CONTEXTO_OTRO_PLAZO.search(sentence):
        return False
    if p.CONTEXTO_INSCRIPCION.search(sentence):
        return True
    return bool(p.CONTEXTO_INSCRIPCION.search(window)) and not p.CONTEXTO_OTRO_PLAZO.search(window)


def _rangos(text: str) -> Iterator[tuple[date, date, int, int]]:
    taken: list[tuple[int, int]] = []
    for match in p.RANGO.finditer(text):
        taken.append(match.span())
        start, end = _fecha(match, "a"), _fecha(match, "b")
        if start and end and start <= end:
            yield start, end, match.start(), match.end()
    for match in p.RANGO_ABREVIADO.finditer(text):
        if any(match.start() < high and low < match.end() for low, high in taken):
            continue
        end = _fecha(match, "b")
        if end is None:
            continue
        month = p.MESES[match["am"]] if match["am"] else end.month
        try:
            start = date(end.year - (month > end.month), month, int(match["ad"]))
        except ValueError:
            continue
        if start <= end:
            yield start, end, match.start(), match.end()


def _inscripcion(doc: Document) -> Iterator[FieldResult]:
    for start, end, low, high in _rangos(doc.busqueda):
        if not _es_plazo_de_inscripcion(doc.busqueda, low):
            continue
        for campo, value in ((INICIO, start), (FIN, end)):
            yield doc.resultado(campo, value.isoformat(), BASE, low, high, "REG-FECHA-03", seccion="plazos")


def _aperturas(doc: Document) -> Iterator[FieldResult]:
    """The first day alone, with no closing date. Several different days become a conflict."""
    for match in p.APERTURA.finditer(doc.busqueda):
        value = _fecha(match, "f")
        if value is None or p.APERTURA_HUECO_AJENO.search(match["gap"]):
            continue
        rule = _regla_formato(match, "f")
        yield doc.resultado(INICIO, value.isoformat(), BASE, match.start(), match.end(), rule, seccion="plazos")

    listing = False
    for paragraph in doc.parrafos:
        text = doc.busqueda[paragraph.inicio : paragraph.fin]
        if p.APERTURA_LISTA.search(text):
            listing = True
            continue
        if not listing:
            continue
        if not p.ELEMENTO_LISTA.match(text):
            listing = False
            continue
        # Only the date that closes the item: later text of the paragraph is something else.
        match = p.FECHA.search(text)
        if match and (value := _fecha(match, "f")):
            low, high = paragraph.inicio + match.start(), paragraph.inicio + match.end()
            rule = _regla_formato(match, "f")
            yield doc.resultado(INICIO, value.isoformat(), BASE, low, high, rule, seccion="plazos")


def _sorteo(doc: Document) -> Iterator[FieldResult]:
    seen: set[int] = set()
    for regex in p.SORTEO:
        for match in regex.finditer(doc.busqueda):
            groups = match.groupdict()
            gaps = " ".join(groups.get(name) or "" for name in ("gap", "gap2"))
            position = match.start("fd") if match["fd"] else match.start("fnd")
            value = _fecha(match, "f")
            if value is None or position in seen or p.SORTEO_HUECO_AJENO.search(gaps):
                continue
            if _es_de_norma(doc.busqueda, position):
                continue
            seen.add(position)
            rule = _regla_formato(match, "f")
            yield doc.resultado(SORTEO, value.isoformat(), BASE, match.start(), match.end(), rule, seccion="plazos")


def _periodo(segment: str) -> tuple[str, int, int, str] | None:
    """The first period written in ``segment``: (value, from, to, rule)."""
    found: list[tuple[int, int, int, str, str]] = []  # (from, priority, to, value, rule)
    for match in p.ENTREGA_TRIMESTRE.finditer(segment):
        quarter = p.TRIMESTRES[match["t"] or match["t2"] or match["t3"]]
        year = match["y"] or match["y2"]
        found.append((match.start(), 0, match.end(), f"{year}-T{quarter}", "REG-FECHA-01"))
    full: list[tuple[int, int]] = []
    for match in p.FECHA.finditer(segment):
        full.append(match.span())
        value = _fecha(match, "f")
        if value and not _es_de_norma(segment, match.start()):
            found.append((match.start(), 1, match.end(), f"{value:%Y-%m}", _regla_formato(match, "f")))
    for match in p.ENTREGA_MES.finditer(segment):
        # The month inside a full date is already covered (or was rejected with it).
        if not any(low <= match.start() < high for low, high in full):
            value = f"{match['y']}-{p.MESES[match['m']]:02d}"
            found.append((match.start(), 2, match.end(), value, "REG-FECHA-01"))
    for match in p.ENTREGA_ANO.finditer(segment):
        found.append((match.start(), 3, match.end(), match["y"], "REG-FECHA-01"))
    if not found:
        return None
    start, _, end, value, rule = min(found)
    return value, start, end, rule


def _entrega(doc: Document) -> Iterator[FieldResult]:
    seen: set[int] = set()
    for context in p.CONTEXTO_ENTREGA.finditer(doc.busqueda):
        paragraph = doc.parrafo_en(context.start())
        if paragraph is None:
            continue
        tail = doc.busqueda[context.end() : min(paragraph.fin, context.end() + p.HUECO_ENTREGA + 40)]
        # Stop at the end of the sentence (a dot inside a numeric date does not count).
        tail = re.split(r";|\.(?=\s|$)", tail)[0]
        period = _periodo(tail)
        if period is None:
            continue
        value, start, end, rule = period
        position = context.end() + start
        if position in seen or start > p.HUECO_ENTREGA or p.PLAZO_RELATIVO.search(tail):
            continue
        if p.ENTREGA_HUECO_AJENO.search(tail[:start]):
            continue
        seen.add(position)
        yield doc.resultado(ENTREGA, value, BASE, context.start(), context.end() + end, rule, seccion="plazos")


class FechasExtractor:
    nombre = "fechas"
    version = "1.0.0"
    campos_soportados = frozenset({INICIO, FIN, SORTEO, ENTREGA})

    def extract(self, doc: Document, ctx: ExtractionContext) -> list[FieldResult]:
        return [*_inscripcion(doc), *_aperturas(doc), *_sorteo(doc), *_entrega(doc)]
