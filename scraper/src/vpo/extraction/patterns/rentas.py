"""Patterns for rents: REG-RENTA-01..04 and the VAT / community fee markers (ARCHITECTURE.md §5.3)."""

from __future__ import annotations

import re

from . import NUM_RE, WORD_RE

RENTA_MINIMA = 150.0
RENTA_MAXIMA = 2500.0

# -- REG-RENTA-01: table headers (folded text) --------------------------------------------------

CAB_DORMITORIOS = re.compile(r"dormitorio|\bdorms?\b|habitacion|\bn[o.]{0,3}\s*d\b")
CAB_TIPOLOGIA = re.compile(r"tipologia|^tipo\b|\btipo de vivienda")
CAB_VIVIENDA = re.compile(r"^(?:tipo de )?viviendas?\.?$")
CAB_RENTA_FUERTE = re.compile(r"\brentas?\b|alquiler|arrendamiento|mensualidad")
CAB_RENTA_DEBIL = re.compile(r"\bprecio|\bimporte|\bcuota")
CAB_MENSUAL = re.compile(r"mensual|\bmes\b|\brentas?\b|alquiler|arrendamiento")
# A column carrying any of these is not the monthly rent of a dwelling.
CAB_NO_RENTA = re.compile(
    r"anual|/\s*ano\b|\bal ano\b|\bpor ano\b|venta|precio[^;]{0,25}compra|ingreso|fianza|deposito|garantia"
    r"|\baval|m2|\bm 2\b|metro|iprem|reserva|capita|familiar|convivencia|declaracion|seguro|suministro"
    r"|subvencion|ayuda|bonific|descuento|esfuerzo|%|superficie|\bsup\b\.?|modulo|miembro|^gastos"
)
CAB_GASTOS = re.compile(r"gastos|\bibi\b|comunidad(?! de madrid)")
CAB_ANEJO = re.compile(r"garaje|aparcamiento|trastero|anejo")
CAB_GARAJE = re.compile(r"garaje|aparcamiento")
CAB_TRASTERO = re.compile(r"trastero")
# "renta con garaje", "vivienda + trastero": a combined rent, not the price of the annex alone.
CAB_COMBINADA = re.compile(
    r"viviend|\btotal|conjunto|(?:\bcon\b|\+|\bincl\w*|\bmas\b)\s*(?:plaza de |el |la )?(?:garaje|trastero|anejo|aparc)"
)
CAB_MINIMA = re.compile(r"minim|\bdesde\b|\bmin\b")
CAB_MAXIMA = re.compile(r"maxim|\bhasta\b|\bmax\b")
CAB_PRECIO_ANEJO = re.compile(r"renta|precio|alquiler|importe|cuota|€|\beuros?\b")
CAB_NO_PRECIO_ANEJO = re.compile(
    r"superficie|\bsup\b|m2|numero|\bn[o.]{1,2}\s*(?:de\s+)?plazas|unidades|anual|venta|fianza|deposito"
)
CAB_SOLO_ANEJO = re.compile(r"^(?:plazas? de )?(?:garaje|aparcamiento|trastero)s?(?: \(\d\))?$")
CAB_NUM_VIVIENDAS = re.compile(
    r"(?:\bn[o.]{0,3}|\bnum(?:ero|\.)?|\bcantidad|\btotal)\s*(?:de\s+)?(?:viviendas|viv\.?(?![a-z])|uds\.?|unidades)"
    r"|^(?:viviendas|unidades|uds\.?)(?: \(\d\))?$"
)
CAB_UTIL = re.compile(r"\butil(?:es)?\b")
CAB_NO_UTIL = re.compile(r"construid|renta|precio|alquiler|garaje|aparcamiento|trastero|terraza|€|euros")
# Columns that only make sense when every row is one dwelling.
CAB_IDENTIFICADOR = re.compile(
    r"\bportal\b|\bplanta\b|\bescalera\b|\bpuerta\b|\bletra\b|\bpiso\b|\bbloque\b|\bfinca\b|\breferencia\b"
    r"|\b(?:n[o.]{0,3}|numero)\s*(?:de\s+)?vivienda\b|\bid(?:entificador)?\b"
)
# A table whose title says this is never a table of monthly dwelling rents.
TITULO_EXCLUIDO = re.compile(r"ingresos|fianza|deposito|venta|anual|iprem")

# -- table cells --------------------------------------------------------------------------------

CELDA_FILA_AJENA = re.compile(r"\b(?:garajes?|trasteros?|local(?:es)?|aparcamientos?|plazas? de)\b")
CELDA_FILA_RESUMEN = re.compile(r"\b(?:sub)?total(?:es)?\b|\bmedia\b|\bpromedio\b")
_DORM = rf"(?P<d>\d|cinco|{WORD_RE})"
CELDA_TIPOLOGIA = re.compile(rf"(?<![\w.,]){_DORM}\s*(?:dormitorios?|dorms?\b\.?|d\b\.?|habitacion(?:es)?)")
CELDA_VARIAS = re.compile(r"\d\s*(?:y|o|-|–|/|,|a)\s*\d\s*(?:d|habitac)|\b(?:y|o) mas\b")
CELDA_ESTUDIO = re.compile(r"\bestudios?\b")
CELDA_ADAPTADA = re.compile(r"adaptad|\bpmr\b|movilidad reducida")

# -- REG-RENTA-02 / 03: running text ------------------------------------------------------------

DINERO = rf"(?<![\d.,]){NUM_RE}"
EUROS = r"(?:€|euros?\b|eur\b)"
TEXTO_DORMITORIOS = re.compile(
    r"(?<![\w.,/\-])(?P<d>\d(?=\s*d(?:orm|\b))|(?:un|uno|una|dos|tres|cuatro)(?=\s+dormitorio))"
    r"\s*(?:dormitorios?\b|dorms?\b\.?|d\b(?![/'\-]))"
)
# "de 1, 2 y 3 dormitorios": the amount that follows belongs to none of them alone.
TEXTO_LISTA_DORMITORIOS = re.compile(r"(?:\b\d|\bun[oa]?|\bdos|\btres)\s*(?:,|\by\b|\bo\b|\ba\b|\bal\b|-|/)\s*$")
TEXTO_HORQUILLA = re.compile(
    rf"\b(?:desde|entre|de)\s+(?:los\s+)?(?P<a>{DINERO})\s*(?:{EUROS})?[^.;]{{0,20}}?"
    rf"\b(?:hasta|y|a)\s+(?:los\s+)?(?P<b>{DINERO})\s*{EUROS}"
)
TEXTO_IMPORTE = re.compile(rf"(?P<n>{DINERO})\s*{EUROS}")
TEXTO_MENSUAL = re.compile(r"^\s*(?:/\s*mes\b|al mes\b|por mes\b|cada mes\b|mensual(?:es|mente)?\b)")
TEXTO_NO_MENSUAL = re.compile(
    r"^\s*(?:/\s*m2|/\s*m\b|por m(?:2|etro)|el m2|anual|al ano|/\s*ano|por ano|de (?:fianza|ingresos|deposito|garantia)"
    r"|en concepto de|por (?:plaza|garaje|trastero)|de (?:garaje|trastero))"
)
TEXTO_CONTEXTO_RENTA = re.compile(r"\brentas?\b|\balquiler|\barrendamiento|mensual|\bal mes\b|/\s*mes\b")
# Words that make an amount something other than the rent of a dwelling.
TEXTO_AJENO = re.compile(
    r"garaje|trastero|aparcamiento|fianza|deposito|garantia|\baval|ingres|venta|compraventa|\bcompra\b|anual"
    r"|\bal ano\b|iprem|seguro|gastos|suministro|reserva|ayuda|subvencion|bonific|descuento|penaliz|sancion"
    r"|indemniz|deduccion|patrimonio|renta (?:familiar|disponible|per capita)|declaracion"
)

# -- REG-RENTA-04 -------------------------------------------------------------------------------

TEXTO_EUR_M2 = re.compile(rf"{DINERO}\s*{EUROS}\s*(?:/|por\s+)\s*m2(?:\s*utile?s?)?(?:\s*(?:/|al|por)\s*mes)?")

# -- VAT and community fees ---------------------------------------------------------------------

_GASTOS = r"(?:los\s+)?gastos\s+de\s+(?:la\s+)?comunidad"
# (note, rule id, pattern)
MARCADORES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "IVA no incluido",
        "REG-RENTA-IVA",
        re.compile(r"\biva\s+no\s+incluido|\bmas\s+(?:el\s+)?iva\b|\+\s*iva\b|\bsin\s+incluir\s+(?:el\s+)?iva\b"),
    ),
    ("IVA incluido", "REG-RENTA-IVA", re.compile(r"\biva\s+incluido|(?<!no )\bincluido\s+(?:el\s+)?iva\b")),
    (
        "Gastos de comunidad no incluidos",
        "REG-RENTA-GASTOS",
        re.compile(
            rf"{_GASTOS}\s+no\s+(?:estan\s+)?incluidos|\b(?:no\s+incluyen?|sin\s+incluir|no\s+incluidos)\s+{_GASTOS}"
        ),
    ),
    (
        "Gastos de comunidad incluidos",
        "REG-RENTA-GASTOS",
        re.compile(rf"{_GASTOS}\s+(?:estan\s+)?incluidos|(?<!no )\b(?:incluyen?|incluidos|incluyendo)\s+{_GASTOS}"),
    ),
)
