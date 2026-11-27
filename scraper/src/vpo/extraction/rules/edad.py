"""Applicant age limits (REG-EDAD-01..03), as requirement or quota, and their explicit absence (REG-EDAD-04).

Ages of children, dependants or reduced-mobility quotas and ages mentioned for priorities or paperwork
are not the applicant's age requirement and are skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..base import Document, ExtractionContext, FieldResult
from ..patterns import edad as p
from ..patterns.ingresos import Oracion, oraciones

_CAMPO = "/requisitos/edad"
_NO_EXIGIDOS = "/requisitos/no_exigidos"
_SECCION = "requisitos"
_BASE = {"REG-EDAD-01": 0.85, "REG-EDAD-02": 0.9, "REG-EDAD-03": 0.8}
# Outside these bounds the figure is about children, buildings or a typo.
_MINIMOS = range(16, 81)
_MAXIMOS = range(25, 100)


@dataclass(frozen=True)
class _Limite:
    inicio: int  # offsets inside the sentence
    fin: int
    minimo: int | None
    maximo: int | None
    regla: str


class EdadExtractor:
    nombre = "edad"
    version = "1.0.0"
    campos_soportados = frozenset({_CAMPO, _NO_EXIGIDOS})

    def extract(self, doc: Document, ctx: ExtractionContext) -> list[FieldResult]:
        found: list[FieldResult] = []
        for oracion in oraciones(doc):
            if "edad" not in oracion.texto and "anos" not in oracion.texto:
                continue
            if p.AJENO_ORACION_RE.search(oracion.texto) or p.AJENO_ORACION_RE.search(oracion.entradilla):
                continue
            found += _sin_limite(doc, oracion)
            found += _limites_de(doc, oracion)
        return found


def _sin_limite(doc: Document, oracion: Oracion) -> list[FieldResult]:
    texto = oracion.texto
    match = p.SIN_LIMITE_RE.search(texto)
    if not match or p.SIN_LIMITE_MATIZADO_RE.search(texto) or p.AJENO_CERCA_RE.search(texto):
        return []
    return [
        doc.resultado(
            _NO_EXIGIDOS,
            "edad",
            0.9,
            oracion.inicio + match.start(),
            oracion.inicio + match.end(),
            "REG-EDAD-04",
            seccion=_SECCION,
        )
    ]


def _leer(texto: str) -> list[_Limite]:
    """Every age limit written in the sentence, without judging its context."""
    limites: list[_Limite] = []

    def libre(match: re.Match[str]) -> bool:
        return not any(match.start() < x.fin and x.inicio < match.end() for x in limites)

    for pattern in (p.CUMPLIDOS_RE, p.RANGO_RE, p.RANGO_DE_A_RE):
        for match in pattern.finditer(texto):
            minimo, maximo = int(match.group("a")), int(match.group("b"))
            if pattern is p.CUMPLIDOS_RE:
                maximo -= 1
            if libre(match):
                limites.append(_Limite(match.start(), match.end(), minimo, maximo, "REG-EDAD-02"))

    # Inclusive and negated wordings first: they contain the plain ones.
    for pattern, es_maximo, ajuste in (
        (p.MAXIMO_INCLUIDO_RE, True, 0),
        (p.SIN_CUMPLIR_RE, True, -1),
        (p.MINIMO_RE, False, 0),
        (p.MENOR_QUE_RE, True, -1),
    ):
        for match in pattern.finditer(texto):
            if not libre(match):
                continue
            negado = bool(p.NEGADO_RE.search(texto[: match.start()]))
            if negado and pattern in (p.MINIMO_RE, p.MENOR_QUE_RE):
                continue  # a negation the patterns do not spell out
            valor = int(match.group("n")) + ajuste
            if p.AMBIGUO_RE.match(texto[match.end() :]):
                valor = -1  # out of bounds: dropped below, and it blocks the plainer patterns
            minimo, maximo = (None, valor) if es_maximo else (valor, None)
            regla = "REG-EDAD-01" if es_maximo else "REG-EDAD-03"
            limites.append(_Limite(match.start(), match.end(), minimo, maximo, regla))
    return sorted(limites, key=lambda x: x.inicio)


def _plausible(limite: _Limite) -> bool:
    minimo, maximo = limite.minimo, limite.maximo
    if (minimo is not None and minimo not in _MINIMOS) or (maximo is not None and maximo not in _MAXIMOS):
        return False
    return minimo is None or maximo is None or minimo < maximo


def _unir(texto: str, limites: list[_Limite]) -> list[_Limite]:
    """'mayores de 18 y menores de 35' is one range."""
    if len(limites) != 2:
        return limites
    primero, segundo = limites
    complementarios = (primero.minimo is None) != (segundo.minimo is None) and (primero.maximo is None) != (
        segundo.maximo is None
    )
    if not complementarios or not p.UNION_RE.match(texto[primero.fin : segundo.inicio]):
        return limites
    minimo = primero.minimo if primero.minimo is not None else segundo.minimo
    maximo = primero.maximo if primero.maximo is not None else segundo.maximo
    unido = _Limite(primero.inicio, segundo.fin, minimo, maximo, "REG-EDAD-02")
    return [unido] if _plausible(unido) else limites


def _tipo(doc: Document, oracion: Oracion, limite: _Limite) -> str | None:
    """'cupo', 'requisito' or None when the figure is neither."""
    inicio, fin = oracion.inicio + limite.inicio, oracion.inicio + limite.fin
    parrafo = doc.parrafo_en(inicio)
    cerca = doc.busqueda[max(parrafo.inicio, inicio - p.CERCA_CUPO) : min(parrafo.fin, fin + p.CERCA_CUPO)]
    if p.CUPO_RE.search(cerca) or p.CUPO_RE.search(oracion.entradilla):
        return "cupo"
    if p.PREFERENCIA_RE.search(oracion.texto) or p.PREFERENCIA_RE.search(oracion.entradilla):
        return None
    if oracion.seccion == _SECCION or p.SENAL_REQUISITO_RE.search(f"{oracion.entradilla} {oracion.texto}"):
        return "requisito"
    return None


def _limites_de(doc: Document, oracion: Oracion) -> list[FieldResult]:
    texto = oracion.texto
    leidos = [
        x
        for x in _leer(texto)
        if _plausible(x)
        and not p.AJENO_CERCA_RE.search(texto[max(x.inicio - p.CERCA, 0) : x.fin + p.CERCA])
        and not p.PERIODO_ANTES_RE.search(texto[max(x.inicio - p.CERCA, 0) : x.inicio])
    ]
    found = []
    for limite in _unir(texto, leidos):
        # "18 anos o menor emancipado": the minimum is not strictly the figure.
        if p.EMANCIPADO_RE.search(texto) and limite.minimo is not None and limite.minimo <= 18:
            continue
        tipo = _tipo(doc, oracion, limite)
        if tipo is None:
            continue
        found.append(
            doc.resultado(
                _CAMPO,
                {"min": limite.minimo, "max": limite.maximo, "tipo": tipo},
                _BASE[limite.regla],
                oracion.inicio + limite.inicio,
                oracion.inicio + limite.fin,
                limite.regla,
                seccion=_SECCION,
            )
        )
    return found
