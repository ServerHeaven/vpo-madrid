"""Garage and storage room: REG-ANEJO-01..03 (ARCHITECTURE.md §5.3).

Nothing mentioned yields nothing; "no" needs an explicit negation.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..base import CAMPO_GARAJE, CAMPO_TRASTERO, Document, ExtractionContext, FieldResult
from ..patterns import anejos as p
from ..patterns import to_number
from .rentas import frases

BASE = 0.85


@dataclass(frozen=True)
class _Dato:
    campo: str
    disponibilidad: str | None
    precio: float | None
    inicio: int
    fin: int
    regla: str
    normativo: bool


def _campos(grupo: str) -> list[str]:
    fields = []
    if p.ES_GARAJE.search(grupo):
        fields.append(CAMPO_GARAJE)
    if p.ES_TRASTERO.search(grupo):
        fields.append(CAMPO_TRASTERO)
    return fields


def _disponibilidad(frase: str, start: int, end: int) -> tuple[str, str, int, int] | None:
    """(value, rule, from, to) of what is said about the annex group at frase[start:end]."""
    if p.CONDICIONAL.search(frase) or "y/o" in frase[start:end]:
        return None
    before, after = frase[:start], frase[end:]
    negation = p.SIN_ANTES.search(before)
    if negation:
        # "quien no disponga de garaje" speaks about the applicant.
        if p.SOLICITANTE.search(before):
            return None
        return "no", "REG-ANEJO-01", negation.start(), end
    optional = p.OPCIONAL_DESPUES.match(after)
    if optional and not p.CORTE.search(optional["gap"]):
        return "opcional", "REG-ANEJO-02", start, end + optional.end()
    optional = p.OPCIONAL_ANTES.search(before)
    if optional:
        return "opcional", "REG-ANEJO-02", optional.start(), end
    included = p.INCLUIDO_DESPUES.match(after)
    if included and not p.CORTE.search(included["gap"]):
        return "incluido", "REG-ANEJO-01", start, end + included.end()
    included = p.INCLUIDO_ANTES.search(before)
    negated = included and (p.NEGADO_ANTES.search(before[: included.start()]) or p.NEGACION.search(included[0]))
    if included and not negated:
        return "incluido", "REG-ANEJO-01", included.start(), end
    return None


def _precio(frase: str, start: int, end: int) -> tuple[float, int, int] | None:
    """(monthly price, from, to) for the single annex at frase[start:end]."""
    before = frase[:start]
    candidates = []
    # "plaza de garaje: 60 euros al mes"
    match = p.IMPORTE.search(frase, end)
    if match and match.start() - end <= p.HUECO_PRECIO:
        if not p.PRECIO_CORTE.search(frase[end : match.start()]) and not p.CON_VIVIENDA.search(before):
            candidates.append((match, start, match.end()))
    # "60 euros al mes por plaza de garaje"
    for previous in p.IMPORTE.finditer(before):
        link = p.ENLACE_PRECIO.match(before[previous.end() :])
        if link and previous.end() + link.end() == len(before):
            candidates.append((previous, previous.start(), end))
    for match, low, high in candidates:
        value = to_number(match["n"])
        if value is None or not p.PRECIO_MINIMO <= value <= p.PRECIO_MAXIMO:
            continue
        window = frase[max(low - 40, 0) : high + 30]
        if p.PRECIO_AJENO.search(window) or not p.MENSUAL.search(frase):
            continue
        return value, low, high
    return None


def _datos(doc: Document) -> list[_Dato]:
    found: list[_Dato] = []
    for offset, original in frases(doc):
        # Same length, so offsets stay valid.
        frase = p.RUIDO.sub(lambda m: "#" * len(m.group()), original)
        if p.VENTA.search(frase):
            continue
        for group in p.GRUPO.finditer(frase):
            fields = _campos(group.group())
            paragraph = doc.parrafo_en(offset + group.start())
            normative = bool(paragraph and paragraph.normativo)
            availability = _disponibilidad(frase, group.start(), group.end())
            # A price for "garaje y trastero" together belongs to neither alone.
            price = _precio(frase, group.start(), group.end()) if len(fields) == 1 else None
            for campo in fields:
                if availability:
                    value, rule, low, high = availability
                    found.append(_Dato(campo, value, None, offset + low, offset + high, rule, normative))
                if price:
                    amount, low, high = price
                    found.append(_Dato(campo, None, amount, offset + low, offset + high, "REG-ANEJO-03", normative))
    return found


def _combinar(data: list[_Dato]) -> list[tuple[str, float | None]]:
    """Compatible statements (availability here, price there) make one value; the others stay apart."""
    kinds = list(dict.fromkeys(d.disponibilidad for d in data if d.disponibilidad))
    prices = list(dict.fromkeys(d.precio for d in data if d.precio is not None))
    if "no" in kinds and prices:
        return [(kind, None) for kind in kinds] + [("desconocido", price) for price in prices]
    return [(kind, price) for kind in kinds or ["desconocido"] for price in prices or [None]]


class AnejosExtractor:
    nombre = "anejos"
    version = "1.0.0"
    campos_soportados = frozenset({CAMPO_GARAJE, CAMPO_TRASTERO})

    def extract(self, doc: Document, ctx: ExtractionContext) -> list[FieldResult]:
        found = _datos(doc)
        results: list[FieldResult] = []
        for campo in (CAMPO_GARAJE, CAMPO_TRASTERO):
            data = [d for d in found if d.campo == campo]
            data = [d for d in data if not d.normativo] or data
            if not data:
                continue
            for kind, price in _combinar(data):
                source = next(
                    (d for d in data if d.disponibilidad == kind),
                    next((d for d in data if price is not None and d.precio == price), data[0]),
                )
                value = {"disponibilidad": kind, "precio_mensual_eur": price}
                results.append(
                    doc.resultado(campo, value, BASE, source.inicio, source.fin, source.regla, seccion="rentas")
                )
        return results
