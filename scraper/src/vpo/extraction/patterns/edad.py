"""Age patterns (ARCHITECTURE.md 5.3, REG-EDAD-01..04). They run on ``Document.busqueda``."""

from __future__ import annotations

import re


def _edad(group: str) -> str:
    """A two digit age, possibly written in words first: 'treinta y cinco (35)'."""
    return rf"(?:[a-z]+(?:\s+y\s+[a-z]+)?\s*\(\s*)?(?<![\d.,])(?P<{group}>\d{{2}})(?![\d.,]\d)(?:\s*\))?"


_ANOS = r"\s+anos\b"
_AUXILIAR = r"(?:(?:podran?|pueden?|deberan?|deben?)\s+)?(?:(?:ser|sean|sea)\s+)?"  # "no podra ser mayor de"
# "18 y menores de 35 anos": the first figure borrows the unit of the second.
_ANOS_O_SIGUE = r"(?:\s+anos\b(?:\s+de\s+edad)?|(?=\s*,?\s*(?:y|e)\s+(?:ser\s+)?(?:menor|no\s+)))"

# REG-EDAD-02
RANGO_RE = re.compile(
    r"\bentre\s+(?:los\s+)?" + _edad("a") + r"(?:\s+anos)?\s+y\s+(?:los\s+)?" + _edad("b") + _ANOS
)
RANGO_DE_A_RE = re.compile(
    r"\b(?:de|desde)\s+(?:los\s+)?" + _edad("a") + r"(?:\s+anos)?\s+(?:a|hasta)\s+(?:los\s+)?" + _edad("b") + _ANOS
    + r"(?=\s+de\s+edad)"
)
CUMPLIDOS_RE = re.compile(
    r"\bhaber\s+cumplido\s+(?:los\s+)?" + _edad("a") + _ANOS
    + r"(?:\s+de\s+edad)?\s*,?\s*y\s+no\s+(?:haber\s+)?cumplido\s+(?:los\s+)?" + _edad("b") + _ANOS
)

# REG-EDAD-01: the figure is the first excluded age (max = n - 1) ...
MENOR_QUE_RE = re.compile(
    r"\b(?:menor(?:es)?\s+(?:de|que|a)\s+|edad\s+(?:sea\s+)?inferior\s+a\s+(?:los\s+)?)" + _edad("n") + _ANOS
)
SIN_CUMPLIR_RE = re.compile(
    r"\bno\s+(?:haber|hayan?|han|tener|tengan?)\s+(?:cumplid[oa]s?\s+(?:los\s+)?|alcanzado\s+(?:la\s+)?edad\s+de\s+)"
    + _edad("n")
    + _ANOS
)
# ... or the last accepted one (max = n).
MAXIMO_INCLUIDO_RE = re.compile(
    r"(?:\bmenor(?:es)?\s+o\s+igual(?:es)?\s+(?:de|que|a)\s+"
    r"|\bedad\s+maxima\s+(?:de\s+|sera\s+de\s+)?"
    r"|\bedad\s+(?:sea\s+)?(?:igual\s+o\s+inferior|inferior\s+o\s+igual|no\s+superior)\s+a\s+(?:los\s+)?"
    r"|\bno\s+(?:superar|superen|supere)\s+(?:los\s+)?(?=\d{2}\s+anos\s+de\s+edad)"
    r"|\bno\s+" + _AUXILIAR + r"mayor(?:es)?\s+de\s+"
    r"|\bedad\s+de\s+hasta\s+"
    r"|\bde\s+hasta\s+(?=\d{2}\s+anos\s+de\s+edad))" + _edad("n") + _ANOS
)
# REG-EDAD-03
MINIMO_RE = re.compile(
    r"(?:\bmayor(?:es)?\s+(?:o\s+igual(?:es)?\s+)?(?:de|que|a)\s+"
    r"|\bedad\s+minima\s+(?:de\s+|sera\s+de\s+)?"
    r"|\bedad\s+(?:sea\s+)?(?:igual\s+o\s+superior|superior\s+o\s+igual|no\s+inferior)\s+a\s+(?:los\s+)?"
    r"|\bno\s+" + _AUXILIAR + r"menor(?:es)?\s+de\s+"
    r"|\b(?:haber\s+cumplido|tener\s+cumplidos)\s+(?:al\s+menos\s+)?(?:los\s+)?)" + _edad("n") + _ANOS_O_SIGUE
)
NEGADO_RE = re.compile(r"\bno\s+(?:(?:ser|sea|sean|podran?|pueden?|deberan?|deben?|tener)\s+)*$")
# Wordings whose limit cannot be told apart from its neighbour.
AMBIGUO_RE = re.compile(r"\s*(?:de\s+edad\s*)?,?\s*(?:o\s+(?:menos|mas)\b|inclusive\b|o\s+de\s+\d)")

# REG-EDAD-04
SIN_LIMITE_RE = re.compile(
    r"\bsin\s+(?:limite|limitacion|restriccion|requisito)(?:es|s)?\s+(?:alguno\s+)?(?:de|por\s+razon\s+de)\s+edad\b"
    r"|\bno\s+(?:existen?|hay|se\s+(?:establecen?|exigen?|fijan?|aplican?))\s+(?:ningun\s+)?"
    r"(?:limite|limitacion|requisito|restriccion)(?:es|s)?\s+(?:alguno\s+)?(?:de|por\s+razon\s+de)\s+edad\b"
)
SIN_LIMITE_MATIZADO_RE = re.compile(r"\b(?:salvo|excepto|pero|sino|siempre\s+que|cuando|si)\b|cupo|reserva")

# -- context ----------------------------------------------------------------------------------

# Ages of someone other than the applicant, or periods that are not an age.
AJENO_ORACION_RE = re.compile(r"movilidad|discapacidad|diversidad\s+funcional|\bayudas?\b|subvenc|bonific")
AJENO_CERCA_RE = re.compile(
    r"\bhij[oa]s?\b|descendient|ascendient|a\s+(?:su\s+)?cargo|\bniet[oa]s?\b|acogid|tutelad|\bdependientes?\b"
    r"|\bmiembros\b|unidad\s+(?:familiar|de\s+convivencia)|\bdni\b|\bnif\b|\bnie\b|documentac|\baport|\bfirm"
    r"|certificad|declaracion|fotocopia|\bcopia\b|autorizacion"
)
# Only meaningful before the figure: "no haber cumplido 36 anos al final del plazo" is an age.
PERIODO_ANTES_RE = re.compile(r"antiguedad|\bplazo|duracion|concesion|edificio|vehiculo")
CERCA = 80
PREFERENCIA_RE = re.compile(r"preferen|priorit|prioridad|\bpuntos\b|puntuac|puntuar|baremo|desempate")
CUPO_RE = re.compile(  # makes the limit a quota, not a requirement
    r"\bcupos?\b|\breserva(?:r|ra|ran|n|do|da|dos|das|s)?\b(?!\s+de\s+dominio)|\bcontingente"
    r"|(?:porcentaje|%)\s+de\s+(?:las\s+)?viviendas"
)
CERCA_CUPO = 200
SENAL_REQUISITO_RE = re.compile(
    r"requisit|\bdeb[ea]|\btener\b|\btengan?\b|\bser\b|\bsean?\b|\bestar\b|\bpodran?\b|solicitante|\bedad\b"
    r"|destinad|dirigid|\bjoven|\bpersonas\b|haber\s+cumplido"
)
EMANCIPADO_RE = re.compile(r"emancipa")
UNION_RE = re.compile(r"^[\s,]*(?:y|e)\b[^.;]{0,30}$")
