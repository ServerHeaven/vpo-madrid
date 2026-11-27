"""Patterns for dates: REG-FECHA-01..04 and their context words (ARCHITECTURE.md §5.3)."""

from __future__ import annotations

import re

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}  # fmt: skip
MES = "|".join(MESES)
_DIA_SEMANA = r"(?:(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo),?\s+)?"


def fecha_re(prefix: str) -> str:
    """REG-FECHA-01 or -02 as one alternative, with groups named after ``prefix``."""
    return (
        rf"(?:(?<![\d/.\-])(?P<{prefix}d>\d{{1,2}})\s+de\s+(?P<{prefix}m>{MES})\s+(?:de|del)\s+(?:ano\s+)?"
        rf"(?P<{prefix}y>20\d{{2}})\b"
        rf"|(?<![\d/.\-])(?P<{prefix}nd>\d{{1,2}})(?P<{prefix}s>[/\-.])(?P<{prefix}nm>\d{{1,2}})(?P={prefix}s)"
        rf"(?P<{prefix}ny>20\d{{2}})(?![\d/\-]))"
    )


FECHA = re.compile(fecha_re("f"))

_HORAS = r"(?:las\s+\d{1,2}(?:[:.]\d{2})?\s*(?:horas|h\b\.?)?\s+del?\s+)"
_DIA = rf"(?:(?:el\s+)?(?:proximo\s+)?(?:dia\s+)?{_DIA_SEMANA})"
_INICIO = rf"\b(?:del|desde(?:\s+{_HORAS})?(?:\s*el)?|entre\s+el)\s+(?:{_HORAS})?{_DIA}"
_FIN = rf"(?:,?\s*ambos\s+inclusive,?)?\s+(?:al|hasta(?:\s+{_HORAS})?(?:\s*el)?|y\s+el)\s+(?:{_HORAS})?{_DIA}"
# REG-FECHA-03
RANGO = re.compile(rf"{_INICIO}{fecha_re('a')}{_FIN}{fecha_re('b')}")
# "del 1 al 15 de marzo de 2026", "del 1 de marzo al 15 de abril de 2026"
RANGO_ABREVIADO = re.compile(
    rf"{_INICIO}(?<![\d/.\-])(?P<ad>\d{{1,2}})(?:\s+de\s+(?P<am>{MES}))?{_FIN}{fecha_re('b')}"
)

# "la apertura de las inscripciones ... el dia X"
APERTURA = re.compile(
    r"\bapertura\s+(?:de\s+(?:las\s+|la\s+)?|del\s+)(?:plazo\s+de\s+)?inscripci[a-z]+"
    rf"(?P<gap>[^.;:]{{0,60}}?)\b(?:el\s+dia|el|dia)\s+{fecha_re('f')}"
)
APERTURA_HUECO_AJENO = re.compile(r"anunci|publica|\bantes\b|despues|\bdesde\b|\bhasta\b|\bdias\b|\bmes(?:es)?\b")
# "las inscripciones ... se abriran en las fechas que se indican", followed by one list item per place
APERTURA_LISTA = re.compile(r"\binscripciones\b[^.]{0,120}?\bse\s+abriran\s+en\s+las\s+(?:siguientes\s+)?fechas\b")
ELEMENTO_LISTA = re.compile(r"^\s*[—–\-•·]\s")

# REG-FECHA-04: relative terms never produce a date.
PLAZO_RELATIVO = re.compile(
    r"\b(?:\d+|diez|quince|veinte|treinta)\)?\s+(?:dias|meses)(?:\s+(?:habiles|naturales))?\s+"
    r"(?:a\s+contar\s+)?(?:desde|a partir|siguientes?)"
)

# -- context words ------------------------------------------------------------------------------

CONTEXTO_INSCRIPCION = re.compile(r"\bplazo|presentacion|solicitud|inscripcion|inscribirse")
CONTEXTO_OTRO_PLAZO = re.compile(
    r"subsana|alegacion|reclamacion|recurso|visita|\bfirma|formaliza|renuncia|\bpago\b|empadron|ingresos"
    r"|ejercicio|periodo impositivo|\bobras\b|vigencia|contrato"
)
VENTANA_CONTEXTO = 200
# The date belongs to a law, an official gazette or an agreement.
FECHA_NORMA = re.compile(
    r"(?:\b(?:real\s+)?decreto(?:-ley)?|\borden(?:anza)?|\bley|\bresolucion|\bacuerdo|\breglamento|\bbocm|\bboe"
    r"|\bboletin oficial|\bescritura|\bconvenio|\b\d{1,4}/(?:19|20)?\d{2})\b"
    r"(?:[^.;:()]{0,60}?(?:,|\bde\b|\bfecha\b))?\s*(?:de\s+)?(?:fecha\s+)?(?:el\s+)?(?:dia\s+)?$"
)

_PUBLICO = r"(?:(?:publico|informatico|ante\s+notario)\s+)?"
_EL = rf"(?:el\s+)?(?:proximo\s+)?(?:dia\s+)?{_DIA_SEMANA}"
_CELEBRA = r"(?:celebrar|celebracion|realizar|efectuar|llevar[a-z]*\s+a\s+cabo|tendra\s+lugar|tiene\s+lugar)[a-z]*"
_FECHA_DEL_SORTEO = r"\bfecha\s+(?:prevista\s+)?(?:del|para\s+el|de\s+celebracion\s+del)\s+sorteo"
SORTEO = tuple(
    re.compile(pattern)
    for pattern in (
        # "el sorteo se celebrara el dia X"
        rf"\bsorteo\b(?P<gap>[^.;]{{0,100}}?)\b{_CELEBRA}(?P<gap2>[^.;]{{0,60}}?)\b(?:el|dia)\s+{_EL}{fecha_re('f')}",
        # "Sorteo: X"
        rf"\bsorteo\s*{_PUBLICO}[:\-–]\s*{_EL}{fecha_re('f')}",
        rf"{_FECHA_DEL_SORTEO}\s*:?\s*(?:es\s+|sera\s+)?{_EL}{fecha_re('f')}",
        # "en el sorteo del dia X"
        rf"\bsorteo\s+{_PUBLICO}(?:del?|el)\s+(?:proximo\s+)?(?:dia\s+)?{fecha_re('f')}",
        # "el X se celebrara el sorteo"
        rf"{fecha_re('f')}(?P<gap>[^.;]{{0,40}}?)\b{_CELEBRA}\s+(?:el\s+)?(?:correspondiente\s+)?sorteo\b",
    )
)
SORTEO_HUECO_AJENO = re.compile(
    r"publica(?:ra|do|cion)|lista|bocm|\bplazo|reclama|alegacion|antes|despues|posterior|\bdesde\b|a partir"
    r"|empadron|inscri|solicitud|presenta|\bhasta\b|\bdias\b|\bmeses\b"
)

CONTEXTO_ENTREGA = re.compile(
    r"\bentrega\s+(?:(?:prevista|estimada)\b|de\s+(?:las?\s+)?(?:llaves|viviendas?)\b)"
    r"|\b(?:prevision|fecha)\s+(?:prevista\s+|estimada\s+)?(?:de\s+)?(?:la\s+)?(?:entrega|finalizacion)\b"
    r"(?!\s+(?:de\s+)?(?:la\s+)?(?:solicitud|document|plazo))"
    r"|\b(?:finalizacion|terminacion|fin)\s+de\s+(?:las\s+)?obras?\b"
    r"|\bviviendas\s+(?:se\s+entregaran|seran\s+entregadas)\b"
)
HUECO_ENTREGA = 80
ENTREGA_HUECO_AJENO = re.compile(
    r"decreto|\borden\b|\bley\b|licencia|\bdesde\b|a partir|\bantes\b|despues|posterior|\bplazo de\b|\bdias\b"
    r"|\bmeses\b|solicitud|document|\bsorteo|empadron|ingresos"
)
_ANO = r"(?:de\s+|del\s+)?(?:ano\s+)?(?P<y>20\d{2})\b"
TRIMESTRES = {"primer": 1, "1": 1, "segundo": 2, "2": 2, "tercer": 3, "3": 3, "cuarto": 4, "4": 4}
ENTREGA_TRIMESTRE = re.compile(
    r"(?:\b(?P<t>primer|segundo|tercer|cuarto|[1-4](?=\s*(?:er|o)?\.?\s*trimestre))\s*(?:er|o)?\.?\s*trimestre\s+"
    rf"{_ANO}|\b(?:t(?P<t2>[1-4])|(?P<t3>[1-4])t)\s*(?:de\s+|-\s*|/\s*)?(?P<y2>20\d{{2}})\b)"
)
ENTREGA_MES = re.compile(rf"\b(?P<m>{MES})\s+{_ANO}")
ENTREGA_ANO = re.compile(
    r"(?:\ben|\bpara|\bdurante|\ba lo largo del?|\bfinales\s+del?|\bmediados\s+del?|\bprincipios\s+del?"
    r"|\bsemestre\s+del?|\bano|:|\bprevista|\bestimada)\s+(?:el\s+)?(?:ano\s+)?(?P<y>20\d{2})\b(?![/\-.]\d)"
)
