"""Patterns for garages and storage rooms: REG-ANEJO-01..03 (ARCHITECTURE.md §5.3)."""

from __future__ import annotations

import re

from . import NUM_RE

PRECIO_MINIMO = 5.0
PRECIO_MAXIMO = 300.0

_GARAJE = r"(?:plazas?\s+de\s+)?(?:garajes?|aparcamientos?)(?!\s+(?:de|para)\s+(?:bicicletas?|bicis|motos|patinetes))"
_TRASTERO = r"(?:cuartos?\s+)?trasteros?"
_ANEJO = rf"(?:{_GARAJE}|{_TRASTERO})"
_ART = r"(?:(?:una?|el|la|los|las|su|sus)\s+)?"
# One annex or several coordinated ones: "plaza de garaje y trastero".
GRUPO = re.compile(rf"\b{_ANEJO}(?:\s*(?:,|\by\b|\be\b|\+|\by/o\b)\s*{_ART}{_ANEJO})*\b")
ES_GARAJE = re.compile(r"garaje|aparcamiento")
ES_TRASTERO = re.compile(r"trastero")

# Blanked before looking for predicates: "incluido" there is about taxes or fees.
RUIDO = re.compile(
    r"\b(?:iva|impuestos?|ibi|gastos(?:\s+de\s+(?:la\s+)?comunidad)?)\s+(?:no\s+)?(?:estan?\s+)?incluidos?"
    r"|\b(?:no\s+)?(?:incluid[oa]s?|incluyendo|incluyen?)\s+(?:(?:el|los)\s+)?(?:iva|impuestos|ibi|gastos)"
    r"(?:\s+de\s+(?:la\s+)?comunidad)?"
)
# Partial or conditional statements say nothing about the promotion as a whole.
CONDICIONAL = re.compile(
    r"en su caso|en el caso|en caso|si (?:los? |las? )?(?:hubiere|tuviera|tienen?\b|dispone|existe)|\balgun[oa]s?\b"
    r"|determinad[oa]s|la mayoria|parte de las|\bpodra(?:n)? estar\b|\bpuede(?:n)? estar\b|aquell[oa]s|con o sin"
)
VENTA = re.compile(r"\bventa\b|compraventa")

# REG-ANEJO-02 (checked first: "no vinculado" must not read as "vinculado").
_OPCIONAL = (
    r"(?:opcional(?:es|mente)?\b|no\s+vinculad[oa]s?\b"
    r"|(?:podra[n]?|se\s+podra[n]?|pueden?)\s+(?:ser\s+)?(?:alquila(?:r|rse|d[oa]s?)|arrenda(?:r|rse|d[oa]s?))\b)"
)
OPCIONAL_DESPUES = re.compile(rf"^(?P<gap>[^.;:]{{0,60}}?)\b{_OPCIONAL}")
OPCIONAL_ANTES = re.compile(
    r"(?:\bopcionalmente|\bde (?:forma|manera) opcional|\bcon caracter opcional|\balquiler opcional de"
    r"|\bpodra[n]?\s+(?:alquilar|arrendar)),?[^.;:,]{0,30}$"
)
# REG-ANEJO-01
INCLUIDO_DESPUES = re.compile(
    r"^(?P<gap>[^.;:]{0,60}?)\b(?:incluid[oa]s?|vinculad[oa]s?|anej[oa]s?\s+(?:a\s+(?:la|las|cada)\b|inseparables?))"
    r"(?!\s+en\s+(?:la\s+(?:promocion|documentacion|solicitud|lista|relacion)|el\s+(?:proyecto|edificio|anexo|listado)))"
)
INCLUIDO_ANTES = re.compile(
    r"(?:\b(?:renta|precio|alquiler|vivienda)s?\b[^.;:]{0,40}?\bincluyen?|\bincluyendo|\bincluid[oa]s?)\s+"
    rf"{_ART}$"
)
# Between the annex and its predicate: a new subject or a negation breaks the link.
CORTE = re.compile(
    r"\bviviendas?\s+(?:con|de|que)\b|\bdormitorios?\b|\bsolicitud|\blista|\banexo\b|\bdocumentaci"
    r"|\bno\b(?!\s+vinculad)|\bsin\b|€|\beuros?\b"
)
NEGADO_ANTES = re.compile(r"\bno\s+(?:se\s+)?(?:estan?\s+)?$|\btampoco\s+$")
# "la renta no incluye": the negation sits inside the INCLUIDO_ANTES match.
NEGACION = re.compile(r"\bno\b|\bsin\b|\btampoco\b")
# Explicit negation: the only way to "no".
SIN_ANTES = re.compile(
    r"(?:\bno\s+(?:se\s+)?(?:dispone[n]?|dispondra[n]?|cuenta[n]?|contara[n]?|tiene[n]?|tendra[n]?|hay)"
    r"(?:\s+(?:de|con))?|\bcarecen?\s+de|\b(?:promocion|edificio)\s+sin)"
    rf"\s+{_ART}(?:ni\s+)?$"
)
SOLICITANTE = re.compile(r"solicitante|persona|adjudicatari|arrendatari|inquilin|unidad (?:familiar|de convivencia)")

# REG-ANEJO-03
IMPORTE = re.compile(rf"(?<![\d.,])(?P<n>{NUM_RE})\s*(?:€|euros?\b|eur\b)")
HUECO_PRECIO = 45
PRECIO_CORTE = re.compile(
    r"viviend|dormitorio|\bm2\b|incluid|incluye|garaje|trastero|aparcamiento|venta|fianza|deposito|\by\b|\bcon\b"
)
PRECIO_AJENO = re.compile(
    r"venta|compraventa|\bcompra\b|fianza|deposito|garantia|anual|\bal ano\b|/\s*ano|m2|ingresos|reserva|penaliz"
    r"|sancion|indemniz|multa"
)
# "60 euros al mes por plaza de garaje": what links an amount to the annex that follows it.
ENLACE_PRECIO = re.compile(
    r"^\s*(?:(?:/|al|por)\s*mes\s*|mensuales\s*)?(?:\+\s*iva\s*|mas iva\s*)?(?:por|para)\s+(?:cada\s+|el\s+|la\s+)?"
)
MENSUAL = re.compile(r"/\s*mes\b|\bal mes\b|\bpor mes\b|mensual|\brentas?\b|\balquiler|arrendamiento")
# "vivienda ... con plaza de garaje por 600 euros": the amount is the dwelling's.
CON_VIVIENDA = re.compile(r"viviend[^.;]*(?:\bcon\b|\+|\bincluy\w+|\bincluid\w+|\bmas\b|\by\b)\s+(?:(?:una?|su)\s+)?$")
