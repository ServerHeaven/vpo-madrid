"""Residency registration patterns (ARCHITECTURE.md 5.3, REG-EMP-01..05). They run on ``Document.busqueda``."""

from __future__ import annotations

import re

from . import NUM_RE, WORD_RE

MENCION_RE = re.compile(
    r"\bempadronad[oa]s?(?:/[oa]s)?\b|\bempadronamiento\b"
    r"|\b(?:inscrit[oa]s?|inscripcion|figur\w+|de\s+alta|antiguedad)\b[^.;]{0,40}?\bpadron\b"
)

# REG-EMP-05: the document says registration is not needed.
NEGACION_RE = re.compile(
    r"\bno\s+(?:se\s+)?(?:exig\w+|requi\w+|precis\w+|es|sera|resulta\w*|constituye)\s+"
    r"(?:(?:un\s+)?(?:necesario|preciso|obligatorio|imprescindible|exigible|requisito)\s+)?"
    r"(?:(?:el|estar|encontrarse|hallarse|figurar|un|ningun|requisito\s+(?:de|del)|el\s+requisito\s+(?:de|del))\s+)?"
    r"(?:empadronad[oa]s?\b|empadronamiento\b)"
    r"|\bsin\s+(?:necesidad|requisito|exigencia|obligacion)\s+de\s+(?:estar\s+)?(?:empadronad[oa]s?\b|empadronamiento\b)"
    r"|\bempadronamiento\b[^.;,]{0,40}?\bno\s+(?:es|sera|constituye)\s+(?:un\s+)?(?:requisito|necesario|exigible|obligatorio)"
)
# A negation with a condition, or about a detail of the registration, is not a plain "not required".
NEGACION_MATIZADA_RE = re.compile(
    r"\b(?:sino|pero|bastando|basta|siempre\s+que|aunque|salvo|excepto|cuando|si|solo|unicamente)\b"
    r"|antiguedad|periodo|minim|\bprevi[oa]|con\s+anterioridad|en\s+el\s+momento|comunidad\s+de\s+madrid"
)

# Percentages of dwellings and priorities are not requirements (together with PRIORIDAD_RE).
CUPO_RE = re.compile(r"\d\s*%|por\s+ciento|\bporcentaje|\bvalorar|\bvaloracion|preferente")
# Conditions to receive an aid are not conditions to apply.
AYUDA_RE = re.compile(r"\bayudas?\b|subvenc|bonific")
# Paperwork, post-award duties and household definitions.
DOCUMENTO_RE = re.compile(r"\b(?:certificad\w+|volante|justificante|copia|fotocopia|documento)\b")
PARTICIPIO_RE = re.compile(r"\bempadronad|inscrit")
DOMICILIO_RE = re.compile(
    r"\bempadronad\w*(?:/[oa]s)?\s+(?:(?:todos|juntos|conjuntamente)\s+)?en\s+(?:(?:la|el|un|una|su|dicha|dicho)\s+)?"
    r"(?:mism[oa]\s+)?(?:vivienda|domicilio|inmueble|hogar)\b"
    r"|vivienda\s+(?:adjudicada|arrendada)"
)
SENAL_REQUISITO_RE = re.compile(
    r"\bdeb[ea]|\brequisito|\bexig|necesari|imprescindible|obligatori|\bsolo\b|unicamente|exclusivamente"
    r"|\bestar\b|\besten\b|\bestes\b|encontrarse|hallarse|\bfigurar|\bacredit|antiguedad|al\s+menos|minim"
    r"|dirigid|destinad|\bpodran?\b|\bser\b"
)
# Where the statement about residency stops and the next requirement of the same sentence begins.
CORTE_RE = re.compile(
    r"\b(?:ni|no)\s+(?:ser|haber|disponer|tener|poseer)\b"
    r"|\by\s+(?:no\s+)?(?:ser|tener|disponer|haber|contar|poseer|acreditar\s+(?:unos\s+)?ingresos)\b"
    r"|\btitular|\bingresos\b|adjudicatari"
)

# -- places -----------------------------------------------------------------------------------

_PREP = r"\b(?:en|de|del)\s+"
# REG-EMP-04
COMUNIDAD_RE = re.compile(
    _PREP + r"(?:(?:cualquiera?(?:\s+de\s+los)?|alguno\s+de\s+los|uno\s+de\s+los|un|algun)\s+municipios?\s+"
    r"(?:(?:de|en)\s+)?)?(?:(?:la|el)\s+)?(?:(?:territorio|ambito)(?:\s+territorial)?\s+de\s+(?:la\s+)?)?"
    r"comunidad\s+(?:de\s+madrid|autonoma\s+de\s+madrid)\b"
)
# "municipio de X", "Ayuntamiento de X": what follows is a name.
MUNICIPIO_DE_RE = re.compile(
    r"\b(?:municipio|termino\s+municipal|localidad|ciudad|villa|ayuntamiento)\s+(?:de\s+|del\s+(?=[a-z]))"
)
# "el municipio", "dicha localidad": the municipality of the promotion.
SIN_NOMBRE_RE = re.compile(
    _PREP + r"(?:(?:el|la|este|esta|dicho|dicha|ese|esa|nuestro|el\s+mismo|la\s+misma)\s+)?"
    r"(?:(?:citad[oa]|referid[oa]|mencionad[oa]|propi[oa]|mism[oa])\s+)?"
    r"(?:municipio|termino\s+municipal|localidad|ciudad)\b(?!\s+(?:de|del)\s)"
)
# "empadronado en Getafe": only tried where the name resolves or is written with a capital letter.
EN_NOMBRE_RE = re.compile(r"\ben\s+|\bpadron(?:\s+municipal)?(?:\s+de\s+habitantes)?\s+de\s+")
PALABRA_RE = re.compile(r"\s*([a-z]+(?:-[a-z]+)*)")
ALTERNATIVA_LUGAR_RE = re.compile(r"[\s,]*(?:o|u|y\s*/\s*o)\b[\s,]*(?:(?:bien|en\s+su\s+defecto),?\s+)?")

# -- years and modifiers ----------------------------------------------------------------------

_PALABRAS = rf"(?:{WORD_RE}|quince|veinte)"


def _cantidad(group: str) -> str:
    """A number of years or months, possibly repeated between brackets: 'tres (3)'."""
    return (
        rf"(?:{_PALABRAS}\s*\(\s*)?(?<![\d.,])(?P<{group}>{NUM_RE}|\b{_PALABRAS}\b)"
        r"(?:\s*\))?(?:\s*\(\s*(?:\d+|[a-z]+)\s*\))?"
    )


def _unidad(group: str) -> str:
    return rf"\s+(?P<{group}>anos?|meses|mes)\b(?!\s+de\s+edad)"


OTRAS_PALABRAS = {"quince": 15, "veinte": 20}
_CALIFICATIVO = r"(?:\s+(?:minim[oa]|continuad[oa]|ininterrumpid[oa]|previ[oa]))*"
ANIOS_RE = re.compile(
    # lead-in before the figure
    r"(?:\b(?:antiguedad|anterioridad|antelacion|periodo|plazo|tiempo)"
    + _CALIFICATIVO
    + r"(?:\s+(?:de|en)\s+(?:empadronamiento|residencia|inscripcion)"
    r"(?:\s+en\s+(?:el\s+municipio(?:\s+de)?\s+)?[a-z-]+(?:\s+(?:de|del)\s+[a-z-]+)?)?)?"
    + _CALIFICATIVO
    + r"(?:\s+(?:de(?:\s+al\s+menos)?|superior\s+a|no\s+inferior\s+a|igual\s+o\s+superior\s+a|al\s+menos"
    r"|como\s+minimo))*"
    r"|\bdurante(?:\s+(?:al\s+menos|como\s+minimo|un\s+(?:periodo\s+|plazo\s+)?minimo\s+de|un\s+(?:periodo|plazo)\s+de"
    r"|los\s+ultimos|mas\s+de))?"
    r"|\bal\s+menos(?:\s+(?:durante|desde\s+hace|con))?|\bcomo\s+minimo(?:\s+(?:durante|desde\s+hace|con))?"
    r"|\b(?:un\s+)?minimo\s+de|\bdesde\s+hace(?:\s+(?:al\s+menos|como\s+minimo|mas\s+de))?"
    r"|\b(?:en|con)?\s*los\s+ultimos),?\s+"
    + _cantidad("n")
    + _unidad("u")
    # or the figure first
    + r"|"
    + _cantidad("n2")
    + _unidad("u2")
    + r"(?=,?\s*(?:de\s+(?:antiguedad|antelacion|anterioridad|empadronamiento|residencia|forma|manera)"
    r"|como\s+minimo|(?:inmediatamente\s+)?anteriores|ininterrumpid|continuad|(?:dentro\s+de|en|de)\s+los\s+ultimos))"
)
# Months of a certificate's age or of an upper bound are not a requirement.
MESES_AJENOS_RE = re.compile(r"inferior|maxim|superior\s+a|expedi|emiti|certificad|volante")
# "... within the last 10 years": the figure is the window, not the required seniority.
VENTANA_RE = re.compile(r"\b(?:en|dentro\s+de|de)\s+los\s+(?:ultimos\s+)?\S+\s+anos$")

ININTERRUMPIDO_RE = re.compile(  # REG-EMP-02
    r"ininterrumpid\w*|\bcontinuad(?:o|a|os|as|amente)\b|\bde\s+(?:forma|manera)\s+continua\b"
    r"|inmediatamente\s+anterior(?:es)?"
)
# "no inferior a 5 anos ininterrumpidos" negates the figure, not the continuity.
ININTERRUMPIDO_NEGADO_RE = re.compile(r"\bno\s+(?!(?:inferior|menor)\b)(?:\w+\s+){0,4}$")
ALTERNOS_RE = re.compile(r"\balternos?\b|\balternad|\bo\s+alternativ|no\s+consecutiv")
_TRABAJO = (
    r"(?:trabaj(?:ar|e|en|an|a)\b|(?:hayan?\s+)?trabajado\b"
    r"|(?:desarroll\w+|desempen\w+|ejerc\w+|realiz\w+)\s+(?:(?:una?|su)\s+)?(?:actividad\s+(?:laboral|profesional)|trabajo)"
    r"|(?:(?:tener|tengan?|tenga)\s+)?(?:su\s+)?(?:puesto|centro|lugar)\s+de\s+trabajo)"
)
ALTERNATIVA_TRABAJO_RE = re.compile(  # REG-EMP-03
    r"(?:\bo\b|y\s*/\s*o\b)[\s,]*(?:(?:bien|que|en\s+su\s+defecto),?\s+)?(?:\w+\s+){0,2}?"
    + _TRABAJO
    + r"|"
    + _TRABAJO
    + r"[^.;]{0,80}?\bo\s+(?:bien\s+)?(?:estar\s+)?empadronad"
)
