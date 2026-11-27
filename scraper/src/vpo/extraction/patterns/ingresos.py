"""Income (IPREM) and effort-rate patterns (ARCHITECTURE.md 5.3), plus the sentence splitting that the
income, residency and age rules share. Everything runs on ``Document.busqueda``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from ..base import Document
from . import NUM_RE, WORD_RE

# -- statements -------------------------------------------------------------------------------

# A sentence ends at . ; ! ? before a capital letter or a numbered item, or before a bullet.
_FIN_ORACION = re.compile(
    r"(?<=[.;!?])(?<!\bart\.)(?<!\bnum\.)(?<!\b[nN]\.)\s+(?=[A-ZÁÉÍÓÚÜÑ¿¡\"“(•▪●]|\d{1,2}[.)]\s|[a-z]\)\s)"
    r"|\s+(?=[•▪●‣◦])"
)
_ITEM_LISTA = re.compile(r"^\s*(?:[a-z]\)|\d{1,2}\s?[.)º°]|[ivx]{1,4}\)|[-–—•▪●‣◦*])")
_MAX_TITULO = 90

# Words that turn a figure into a priority or a quota instead of a requirement.
PRIORIDAD_RE = re.compile(
    r"\bcupos?\b|\breserva(?:r|ra|ran|n|do|da|dos|das|s)?\b|\bcontingente|preferen|priorit|prioridad"
    r"|\bbaremo|\bpuntos\b|puntuac|puntuar|desempate"
)


@dataclass(frozen=True)
class Oracion:
    inicio: int  # offsets into Document.texto / busqueda
    fin: int
    texto: str  # busqueda[inicio:fin]
    entradilla: str  # busqueda of the list lead-in or heading above the paragraph, or ""
    seccion: str


def oraciones(doc: Document) -> Iterator[Oracion]:
    """Every sentence of the document with the heading or lead-in that governs it."""
    for index, parrafo in enumerate(doc.parrafos):
        entradilla = _entradilla(doc, index)
        texto = doc.texto[parrafo.inicio : parrafo.fin]
        cortes = [(m.start(), m.end()) for m in _FIN_ORACION.finditer(texto)]
        inicio = 0
        for corte, siguiente in [*cortes, (len(texto), len(texto))]:
            if corte > inicio:
                a, b = parrafo.inicio + inicio, parrafo.inicio + corte
                yield Oracion(a, b, doc.busqueda[a:b], entradilla, parrafo.seccion)
            inicio = siguiente


def _entradilla(doc: Document, index: int) -> str:
    """The paragraph introducing this one: it ends in ':' or is a short heading. List items are skipped."""
    for anterior in range(index - 1, max(index - 13, -1), -1):
        parrafo = doc.parrafos[anterior]
        texto = doc.busqueda[parrafo.inicio : parrafo.fin].rstrip()
        if texto.endswith(":") or (len(texto) <= _MAX_TITULO and not texto.endswith((".", ";", ","))):
            return texto
        if not _ITEM_LISTA.match(texto):
            break
    return ""


# -- amounts in IPREM -------------------------------------------------------------------------

_PALABRA = rf"\b(?:{WORD_RE})\b"
_VALOR = rf"(?:{_PALABRA}\s+coma\s+{_PALABRA}|{NUM_RE}|{_PALABRA})"


def _cantidad(group: str) -> str:
    """A number, optionally repeated between brackets: 'cinco coma cinco (5,5)'."""
    return rf"(?<![\w.,])(?P<{group}>{_VALOR})(?:\s*\(\s*(?P<{group}_bis>{_VALOR})\s*\))?"


NOMBRE_IPREM = (
    r"[\"“'(]?\s*(?:i\.?p\.?r\.?e\.?m(?![a-z])\.?"
    r"|(?:indicador\s+)?publico\s+de\s+rentas?\s+(?:de|con|a)\s+efectos\s+multiples)[\"”')]?"
)
IPREM_RE = re.compile(NOMBRE_IPREM)

# What may sit between "veces" and the name of the index.
_NEXO = (
    r"\s*,?\s*(?:(?:el|al|del|la|de)\s+)?(?:(?:importe|valor|cuantia)\s+(?:(?:anual|mensual)\s+)?(?:del?\s+))?"
    r"(?:(?:referido|citado|mencionado|indicado|vigente)\s+)?(?:(?:indice|indicador)\s+(?=i\.?p))?"
)
_SIGLA_REPETIDA = r"(?:\s*\(\s*i\.?p\.?r\.?e\.?m\.?\s*\))?"
_VECES = r"(?:\s*(?P<{g}>veces\b|vez\b|x\b))?(?P<{m}>\s+y\s+medi[ao]\b)?"

CANTIDAD_IPREM_RE = re.compile(
    _cantidad("n")
    + _VECES.format(g="veces", m="media")
    + rf"(?P<iprem>{_NEXO}{NOMBRE_IPREM}{_SIGLA_REPETIDA}"
    # "... y maximos de 3,5 veces del mismo indicador": the sentence has named it already.
    + r"|\s+(?:(?:del|el|de|al)\s+)?(?:mismo|citado|referido|dicho|mencionado)\s+(?:indicador|indice)\b)?"
)
# REG-IPREM-01: "no pueden superar el resultado de multiplicar por 5,5 el ultimo IPREM".
MULTIPLICAR_RE = re.compile(
    r"\bno\s+(?:\w+\s+){0,2}?(?:superar|superen|exceder(?:\s+de)?)\s+(?:el\s+)?resultado\s+de\s+multiplicar\s+por\s+"
    + _cantidad("n")
    + rf"\s+(?:el\s+)?(?:ultimo\s+)?{NOMBRE_IPREM}"
)
# A figure without "IPREM" after it only counts if the sentence goes on to the other limit or ends.
SIGUE_SIN_NOMBRE_RE = re.compile(r"\s*(?:[,.;)]|$|(?:ni|y|e|o|como)\b)")
SIGUE_OTRO_LIMITE_RE = re.compile(
    r"\s*,?\s*(?:ni|y)\s+(?:no\s+)?(?:(?:podran?|deberan?)\s+)?(?:(?:ser|sean)\s+)?"
    r"(?:superior|inferior|mayor|menor|super[ae]|exced)"
)

# REG-IPREM-03
RANGO_IPREM_RE = re.compile(
    r"\b(?P<prep>entre|desde|de)\s+(?:(?:los|las)\s+)?"
    + _cantidad("a")
    + rf"(?:\s*(?:veces|vez)\b(?P<media_a>\s+y\s+medi[ao]\b)?(?:{_NEXO}{NOMBRE_IPREM}{_SIGLA_REPETIDA})?)?"
    + r"\s*,?\s*(?P<nexo>y|a|hasta)\s+(?:un\s+maximo\s+(?:de\s+)?)?"
    + _cantidad("b")
    + _VECES.format(g="veces_b", m="media_b")
    + rf"{_NEXO}{NOMBRE_IPREM}{_SIGLA_REPETIDA}"
)
NEXOS_DE_RANGO = {"entre": ("y",), "desde": ("a", "hasta"), "de": ("a", "hasta")}

# REG-IPREM-01 / REG-IPREM-02: the last comparator before a figure says which limit it is.
COMPARADOR_RE = re.compile(
    r"(?P<max>\bmaxim[oa]s?\b|\bhasta\b|\btope\b)"
    r"|(?P<min>\bminim[oa]s?\b|\bal\s+menos\b|\ba\s+partir\s+de\b|\bdesde\b)"
    r"|(?P<sup>(?:\bigual(?:es)?\s+o\s+)?\b(?:superior(?:es)?|(?:mayor(?:es)?(?=\s+(?:o\s+igual\s+)?(?:a|que|de)\b"
    r"(?!\s+edad))))\b(?:\s+o\s+igual(?:es)?)?)"
    r"|(?P<verbo>\b(?:super(?:ar|e|en|a|an|ara|aran)|exced(?:er|a|an|e|en|era|eran)|rebas(?:ar|e|en|a|an)"
    r"|sobrepas(?:ar|e|en|a|an))\b)"
    r"|(?P<inf>(?:\bigual(?:es)?\s+o\s+)?\b(?:inferior(?:es)?|(?:menor(?:es)?(?=\s+(?:o\s+igual\s+)?(?:a|que|de)\b"
    r"(?!\s+edad))))\b(?:\s+o\s+igual(?:es)?)?)"
)
# Longest text allowed between each comparator and its figure.
MAX_HUECO = {"max": 80, "min": 80, "sup": 45, "verbo": 45, "inf": 45}
MAX_HUECO_PREPOSICION = {"hasta": 30, "desde": 20, "al menos": 30}
NEGADO_RE = re.compile(
    r"\b(?:no|ni|sin)\s+(?:(?:podran?|puedan?|pueden?|deberan?|deben?|ser|seran?|sean?|resultar|resulten|han"
    r"|ha|de|en|ningun|caso|estar|que|sus|ingresos)\s+){0,6}$"
)
NEGACION_CERCANA_RE = re.compile(r"\b(?:no|ni|sin)\b")
AMBOS_LIMITES_RE = re.compile(r"\b(?:minim[oa]s?\s+y\s+(?:los\s+)?maxim|maxim[oa]s?\s+y\s+(?:los\s+)?minim)")
SUFIJO_RE = re.compile(r"\s*,?\s*(?:como|de)\s+(?P<tipo>maximo|minimo)\b")
HEREDA_RE = re.compile(
    r"^\s*(?:en\s+[^,.;]{0,40}?)?,?\s*\b(?:y|o|u)\s+(?:(?:a|de|hasta)\s+)?$"
    r"|^[^.;:]{0,160}?\bvpp[a-z]*\b[^.;:]{0,20}?\b(?:y|o|u)\s+(?:de\s+)?$"  # "... (VPPB) y 7,5 veces"
)

EXCLUSION_RE = re.compile(
    r"exclui|exclusion|excluy|denegad|denegar|desestim|inadmit|quedaran?\s+fuera"
    r"|\bno\s+(?:podran?|puede[n]?)\s+(?:acceder|participar|solicitar|optar|resultar|ser\s+adjudicatari)"
    r"|\bno\s+tendran?\s+derecho"
)
# Sentences about money that is not the access requirement.
OTRO_ASUNTO_RE = re.compile(
    r"\btramos?\b|\baval(?:es)?\b|\bfianza|\bgarantias?\b|\bdeposito|\bseguro\b|\bayudas?\b|subvenc|bonific"
    r"|descuento|\bexent|\bpodra[n]?\s+ofrecer|excepcionalmente|con\s+caracter\s+excepcional"
)
# A limit that only applies to part of the applicants or of the dwellings.
CONDICION_RE = re.compile(
    r"numeros[ao]s?\b|discapacidad|monoparental|movilidad\s+reducida|\bvictimas?\b|\bjovenes\b|mayores\s+de\s+\d"
    r"|dormitorio|\b(?:\d+|un[ao]?|dos|tres|cuatro|cinco|seis)\s+(?:(?:o|a|y)\s+(?:\w+\s+)?(?:mas\s+)?)?"
    r"(?:miembros?|personas?)\b"
)
SUFIJO_CONDICION_RE = re.compile(r"\s*\(?\s*(?:para|en\s+(?:el\s+)?(?:caso|supuesto)|cuando|si)\b")

# -- payments, year, effort rate --------------------------------------------------------------

PAGAS_RE = re.compile(r"\b(?P<pagas>12|14|doce|catorce)\s+(?:pagas|mensualidades)\b(?!\s+extra)")  # REG-IPREM-05
PAGAS_AJENAS_RE = re.compile(r"nomina|salario|sueldo|trabajador|\bsin\s+(?:incluir\s+)?$")

# REG-IPREM-06
EJERCICIO_RE = re.compile(
    r"(?:\bejercicio(?:\s+(?:fiscal|economico))?"
    r"|\bdeclaracion(?:\s+anual)?\s+(?:de(?:l)?\s+)?(?:la\s+)?(?:renta|irpf"
    r"|impuesto\s+sobre\s+la\s+renta\s+de\s+las\s+personas\s+fisicas)(?:\s*\(\s*irpf\s*\))?"
    r"|\birpf"
    r"|\biprem\)?(?:\s+(?:anual|vigente))?(?:\s+correspondiente)?\s+(?:al?|del?|en|para)(?:\s+el)?"
    r"(?=\s+(?:(?:ano|ejercicio)\s+)?20\d\d))"
    r",?\s*(?:(?:correspondiente\s+)?(?:al|del?)\s+)?(?:(?:ejercicio|ano|periodo)(?:\s+fiscal)?\s+)?(?:de\s+)?"
    r"(?P<y>20\d{2})\b(?!\s*(?:o|y|/|-|a)\s*20\d\d)"
)
EJERCICIO_CONTEXTO_RE = re.compile(r"iprem|ingresos|\brenta\b|\birpf\b|efectos\s+multiples")
EJERCICIO_AJENO_RE = re.compile(r"presupuestos|prorrog|\bcopia\b|fotocopia")  # law quotations, paperwork

_PORCENTAJE = (
    r"(?:[a-z]+(?:\s+y\s+[a-z]+)?(?:\s+por\s+(?:ciento|cien))?\s*\(\s*)?"
    r"(?<![\d.,])(?P<p>\d{1,2})\s*(?:%|por\s+(?:ciento|cien|100)\b)\s*\)?"
)
_DE_LOS_INGRESOS = (
    r"\s*,?\s*(?:de|sobre)\s+(?:(?:los|sus|dichos)\s+|(?:la\s+suma|el\s+total|el\s+conjunto)\s+de\s+(?:los\s+|sus\s+)?"
    r"|la\s+|su\s+)?(?:ingresos\b|renta\s+(?:neta|bruta|disponible|familiar|anual|de\s+la\s+unidad))"
)
_SUPERAR = r"(?:(?:super|exced|supon|represent|sobrepas)\w*|(?:ser|sea|sera|resultar)\s+superior(?:es)?|superior(?:es)?)"
# REG-ESF-01: "la renta no podra superar el 35 % de los ingresos" and the "no destinen mas del" form.
ESFUERZO_RENTA_RE = re.compile(
    r"\bno\s+(?:(?:podra|debera|puede|debe)n?\s+)?(?:en\s+ningun\s+caso\s+)?"
    + _SUPERAR
    + r"\s+(?:en\s+ningun\s+caso\s+)?(?:(?:a|al|el|del|de|un|mas|que)\s+)*"
    + _PORCENTAJE
    + _DE_LOS_INGRESOS
)
ESFUERZO_DESTINO_RE = re.compile(
    r"\bno\s+(?:(?:podra|debera)n?\s+)?(?:destin|dedi[cq])\w*\s+(?:mas\s+(?:del|de\s+un|de))\s+"
    + _PORCENTAJE
    + _DE_LOS_INGRESOS
    + r"[^.;]{0,60}?\b(?:renta|alquiler|arrendamiento)\b"
)
SUJETO_RENTA_RE = re.compile(r"\b(?:renta|alquiler|arrendamiento)\b")
ESFUERZO_TASA_RE = re.compile(r"\btasa\s+(?:maxima\s+)?de\s+esfuerzo\b(?P<hueco>[^%;]{0,40}?)" + _PORCENTAJE)  # REG-ESF-02
ESFUERZO_AJENO_RE = re.compile(r"\bayudas?\b|subvenc|bonific|descuento|reduccion")

# -- stepped table (REG-IPREM-04) -------------------------------------------------------------

_N = rf"(\d{{1,2}}|{WORD_RE})"
MIEMBROS_FORMAS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern), forma)
    for pattern, forma in (
        (rf"{_N}", "uno"),
        (rf"(?:{_N}\s*(?:o|y)\s+mas|{_N}\s*\+|{_N}\s+o\s+superior|(?:>=|≥)\s*{_N}|a\s+partir\s+de\s+{_N})", "desde"),
        (rf"(?:mas\s+de|>)\s*{_N}", "mas_de"),
        (rf"hasta\s+{_N}", "hasta"),
        (rf"(?:de\s+)?{_N}\s*(?:o|y|u|a|-|–|/)\s*{_N}", "rango"),
    )
)
MIEMBROS_RELLENO_RE = re.compile(
    r"\b(?:miembros?|personas?)\b|\bde\s+la\s+unidad(?:\s+(?:familiar|de\s+convivencia))?"
)
CABECERA_MIEMBROS_RE = re.compile(r"miembros?|personas|composicion")
CABECERA_AJENA_RE = re.compile(r"€|euros?|importe|alquiler|\brenta\s+(?:mensual|maxima\s+mensual)|ponderac|coeficiente")
CABECERA_DESCARTADA_RE = re.compile(r"puntos|puntuac|baremo|cupo|preferen|prioridad|ayuda")
CELDA_RELLENO_RE = re.compile(r"\(?\s*i\.?p\.?r\.?e\.?m\.?\s*\)?|\bveces\b|\bvez\b|\bel\b|(?<![a-z])x(?![a-z])")
CELDA_HASTA_RE = re.compile(r"(?:hasta|maximo)\s*:?\s*")
CELDA_RANGO_RE = re.compile(rf"(?:(?:entre|de|desde)\s+)?({NUM_RE})\s*(?:y|a|hasta|-|–)\s*({NUM_RE})")
CELDA_VACIA = ("", "-", "–", "—", "--")
