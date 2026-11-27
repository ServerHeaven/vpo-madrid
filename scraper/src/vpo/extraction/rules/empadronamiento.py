"""Residency registration requirement (REG-EMP-01..04) and its explicit absence (REG-EMP-05).

Only excluding requirements are emitted: priorities, quotas and paperwork are skipped (ADR-002 3), as is
any statement whose place cannot be determined. Mentions that say the same thing with more or less
detail are merged; different years or places stay as separate candidates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..base import Document, ExtractionContext, FieldResult
from ..patterns import empadronamiento as p, to_number
from ..patterns.ingresos import PRIORIDAD_RE, Oracion, oraciones

_CAMPO = "/requisitos/empadronamiento"
_NO_EXIGIDOS = "/requisitos/no_exigidos"
_SECCION = "requisitos"
_MAX_DESPUES = 150
_MAX_ANTES = 100
_MAX_NOMBRE = 6  # words of a municipality name
# Placeholders for places that are not an INE code.
_COMUNIDAD = "comunidad"
_ANAFORA = "anafora"
_DESCONOCIDO = "desconocido"


@dataclass(frozen=True)
class _Lugar:
    inicio: int
    fin: int
    ident: str  # INE code or one of the placeholders


@dataclass(frozen=True)
class _Mencion:
    lugar: str  # INE code or _COMUNIDAD
    anios: float | int | None
    ininterrumpido: bool
    trabajo: bool
    normativo: bool
    resultado: FieldResult


class EmpadronamientoExtractor:
    nombre = "empadronamiento"
    version = "1.0.0"
    campos_soportados = frozenset({_CAMPO, _NO_EXIGIDOS})

    def extract(self, doc: Document, ctx: ExtractionContext) -> list[FieldResult]:
        menciones: list[_Mencion] = []
        negaciones: list[FieldResult] = []
        for oracion in oraciones(doc):
            if not p.MENCION_RE.search(oracion.texto):
                continue
            negacion = p.NEGACION_RE.search(oracion.texto)
            if negacion:
                if not p.NEGACION_MATIZADA_RE.search(oracion.texto):
                    negaciones.append(
                        doc.resultado(
                            _NO_EXIGIDOS,
                            "empadronamiento",
                            0.9,
                            oracion.inicio + negacion.start(),
                            oracion.inicio + negacion.end(),
                            "REG-EMP-05",
                            seccion=_SECCION,
                        )
                    )
                continue
            menciones += _leer_oracion(doc, ctx, oracion)
        return _combinar(menciones) + negaciones


# -- places -----------------------------------------------------------------------------------


def _resolver_nombre(texto: str, desde: int, ctx: ExtractionContext) -> tuple[str, int] | None:
    """The longest municipality name starting at ``desde``: (INE code, end offset)."""
    palabras: list[tuple[str, int]] = []
    pos = desde
    while len(palabras) < _MAX_NOMBRE and (match := p.PALABRA_RE.match(texto, pos)):
        palabras.append((match.group(1), match.end()))
        pos = match.end()
    for largo in range(len(palabras), 0, -1):
        words = [word for word, _ in palabras[:largo]]
        # Hyphenated names are often written without the hyphen: "Rivas Vaciamadrid".
        variantes = [" ".join(words)]
        variantes += [" ".join([*words[:i], f"{words[i]}-{words[i + 1]}", *words[i + 2 :]]) for i in range(largo - 1)]
        for nombre in variantes:
            resuelto = ctx.municipios.resolve(nombre)
            if resuelto:
                return resuelto[0], palabras[largo - 1][1]
    return None


def _lugares(doc: Document, ctx: ExtractionContext, oracion: Oracion) -> list[_Lugar]:
    texto = oracion.texto
    lugares = [_Lugar(m.start(), m.end(), _COMUNIDAD) for m in p.COMUNIDAD_RE.finditer(texto)]

    def libre(inicio: int, fin: int) -> bool:
        return not any(inicio < lugar.fin and lugar.inicio < fin for lugar in lugares)

    for match in p.MUNICIPIO_DE_RE.finditer(texto):
        if not libre(match.start(), match.end()):
            continue
        desde = match.end()
        resuelto = _resolver_nombre(texto, desde, ctx)
        if resuelto is None and match.group().endswith("del "):  # "municipio del Alamo" = "de El Alamo"
            resuelto = ctx.municipios.resolve("el " + texto[desde:].split(" ")[0].strip(",.;:"))
            resuelto = (resuelto[0], desde + len(texto[desde:].split(" ")[0])) if resuelto else None
        ident, fin = resuelto or (_DESCONOCIDO, desde)
        lugares.append(_Lugar(match.start(), fin, ident))
    lugares += [
        _Lugar(m.start(), m.end(), _ANAFORA) for m in p.SIN_NOMBRE_RE.finditer(texto) if libre(m.start(), m.end())
    ]
    for match in p.EN_NOMBRE_RE.finditer(texto):
        if not libre(match.start(), match.end() + 1):
            continue
        resuelto = _resolver_nombre(texto, match.end(), ctx)
        original = doc.texto[oracion.inicio + match.end() : oracion.inicio + len(texto)]
        if resuelto and original[:1].isupper():
            lugares.append(_Lugar(match.start(), resuelto[1], resuelto[0]))
        elif original[:1].isupper() and re.search(r"empadronad\w*(?:/[oa]s)?\s+$", texto[: match.start()]):
            lugares.append(_Lugar(match.start(), match.end(), _DESCONOCIDO))  # "empadronado en Toledo"
    return sorted(lugares, key=lambda lugar: lugar.inicio)


def _lugar_de(
    texto: str, lugares: list[_Lugar], mencion: re.Match[str], inicio: int, fin: int
) -> tuple[str, ...] | None:
    """The identities the mention may refer to within texto[inicio:fin]; None if it is ambiguous."""
    dentro = [lugar for lugar in lugares if lugar.inicio >= inicio and lugar.fin <= fin]
    despues = [x for x in dentro if x.inicio >= mencion.start() and x.inicio - mencion.end() <= _MAX_DESPUES]
    antes = [x for x in dentro if x.fin <= mencion.start() and mencion.start() - x.fin <= _MAX_ANTES]
    if not despues and not antes:
        return None
    identidades = {lugar.ident for lugar in dentro}
    # "en Getafe o en la Comunidad de Madrid": two alternative places cannot be represented.
    for previo, siguiente in zip(dentro, dentro[1:]):
        hueco = texto[previo.fin : siguiente.inicio]
        if previo.ident != siguiente.ident and p.ALTERNATIVA_LUGAR_RE.fullmatch(hueco):
            return None
    if _DESCONOCIDO in identidades:
        return None
    concretas = identidades - {_ANAFORA}
    if len(concretas) > 1 or (_COMUNIDAD in concretas and _ANAFORA in identidades):
        return None
    return tuple(concretas) or (_ANAFORA,)


# -- statements -------------------------------------------------------------------------------


def _clausula(texto: str, mencion: re.Match[str]) -> tuple[int, int]:
    """The part of the sentence about this mention, up to the neighbouring requirements."""
    inicio, fin = 0, len(texto)
    for corte in p.CORTE_RE.finditer(texto):
        if corte.end() <= mencion.start():
            inicio = corte.end()
        elif corte.start() >= mencion.end():
            fin = corte.start()
            break
    return inicio, fin


def _es_requisito(oracion: Oracion, mencion: re.Match[str]) -> bool:
    texto = oracion.texto
    contexto = f"{oracion.entradilla} {texto}"
    if PRIORIDAD_RE.search(contexto) or p.CUPO_RE.search(contexto) or p.DOMICILIO_RE.search(texto):
        return False
    if p.AYUDA_RE.search(contexto):
        return False
    if re.search(r"\bno\s+(?:estar\s+)?$", texto[: mencion.start()]):
        return False
    if p.DOCUMENTO_RE.search(texto) and not p.PARTICIPIO_RE.search(texto):
        return False
    return bool(
        oracion.seccion == _SECCION
        or p.SENAL_REQUISITO_RE.search(texto)
        or re.search(r"requisito|\bdeberan?\b", oracion.entradilla)
    )


def _anios(clausula: str) -> list[tuple[float | int, int]] | None:
    """(years, offset) of each distinct figure; None if the wording cannot be represented."""
    valores: dict[float | int, int] = {}
    ventana = False
    for index, match in enumerate(p.ANIOS_RE.finditer(clausula)):
        if index and p.VENTANA_RE.search(clausula[: match.end()]):
            ventana = True
            continue
        numero = match.group("n") or match.group("n2")
        unidad = match.group("u") or match.group("u2")
        valor = p.OTRAS_PALABRAS.get(numero) or to_number(numero)
        if valor is None:
            return None
        if unidad.startswith("mes"):
            if p.MESES_AJENOS_RE.search(clausula[max(match.start() - 60, 0) : match.end()]):
                continue
            valor = round(valor / 12, 2)
        valores.setdefault(int(valor) if float(valor).is_integer() else float(valor), match.start())
    # "3 anos dentro de los ultimos 5" alone is neither "3 anos" nor "5 anos". With two alternatives
    # ("5 anos o 8 dentro de los ultimos 10") both are kept, so that the conflict surfaces.
    if ventana and len(valores) < 2:
        return None
    return list(valores.items())


def _ininterrumpido(clausula: str, anclas: tuple[int, ...], desde: int, hasta: int | None) -> bool:
    """Whether clausula[desde:hasta] says, near the mention or the figure, that it must be continuous."""
    if p.ALTERNOS_RE.search(clausula[desde:hasta]):
        return False
    return any(
        desde <= match.start() < (len(clausula) if hasta is None else hasta)
        and any(abs(match.start() - ancla) <= _MAX_DESPUES for ancla in anclas)
        and not p.ININTERRUMPIDO_NEGADO_RE.search(clausula[: match.start()])
        for match in p.ININTERRUMPIDO_RE.finditer(clausula)
    )


def _leer_oracion(doc: Document, ctx: ExtractionContext, oracion: Oracion) -> list[_Mencion]:
    texto = oracion.texto
    lugares = _lugares(doc, ctx, oracion)
    parrafo = doc.parrafo_en(oracion.inicio)
    found: list[_Mencion] = []
    leidas: set[tuple[int, int]] = set()
    for mencion in p.MENCION_RE.finditer(texto):
        inicio, fin = _clausula(texto, mencion)
        if (inicio, fin) in leidas or not _es_requisito(oracion, mencion):
            continue
        identidades = _lugar_de(texto, lugares, mencion, inicio, fin)
        if identidades is None:
            continue
        ident = identidades[0]
        if ident == _ANAFORA:
            ident = ctx.municipio_ine
        if ident is None:
            continue
        clausula = texto[inicio:fin]
        anios = _anios(clausula)
        if anios is None:
            continue
        leidas.add((inicio, fin))
        trabajo = bool(p.ALTERNATIVA_TRABAJO_RE.search(clausula))
        posiciones = anios or [(None, 0)]
        for index, (valor, posicion) in enumerate(posiciones):
            # With several alternatives, each one only owns the words up to the next figure.
            desde = posicion if index else 0
            hasta = posiciones[index + 1][1] if index + 1 < len(posiciones) else None
            anclas = (mencion.start() - inicio, posicion if valor is not None else mencion.start() - inicio)
            ininterrumpido = _ininterrumpido(clausula, anclas, desde, hasta)
            comunidad = ident == _COMUNIDAD
            resultado = doc.resultado(
                _CAMPO,
                {
                    "ambito": "comunidad" if comunidad else "municipio",
                    "municipio_ine": None if comunidad else ident,
                    "anios_min": valor,
                    "ininterrumpido": None,
                    "alternativa_trabajo": None,
                },
                0.85 if valor is not None else 0.8,
                oracion.inicio + mencion.start(),
                oracion.inicio + fin,
                "REG-EMP-04" if comunidad else "REG-EMP-01",
                seccion=_SECCION,
            )
            normativo = bool(parrafo and parrafo.normativo)
            found.append(_Mencion(ident, valor, ininterrumpido, trabajo, normativo, resultado))
    return found


def _combinar(menciones: list[_Mencion]) -> list[FieldResult]:
    """One candidate per (place, years): a mention without years adds its details to the others."""
    # A quotation of legislation never lends details to the document's own statements, nor vice versa.
    propias = [m for m in menciones if not m.normativo]
    claves = {(m.lugar, m.anios) for m in propias}
    ajenas = [
        m
        for m in menciones
        if m.normativo and not any(m.lugar == lugar and m.anios in (None, anios) for lugar, anios in claves)
    ]
    return [r for grupo in (propias, ajenas) for r in _combinar_grupo(grupo)]


def _combinar_grupo(menciones: list[_Mencion]) -> list[FieldResult]:
    resultados = []
    for lugar in dict.fromkeys(m.lugar for m in menciones):
        del_lugar = [m for m in menciones if m.lugar == lugar]
        distintos = list(dict.fromkeys(m.anios for m in del_lugar if m.anios is not None))
        for anios in distintos or [None]:
            propias = [m for m in del_lugar if m.anios == anios]
            # Mentions without years only complete the picture when there is no doubt which one they mean.
            sumadas = propias + ([m for m in del_lugar if m.anios is None] if len(distintos) == 1 else [])
            mejor = max(propias, key=lambda m: m.resultado.confianza)
            valor = dict(mejor.resultado.valor)
            valor["ininterrumpido"] = True if any(m.ininterrumpido for m in sumadas) else None
            valor["alternativa_trabajo"] = True if any(m.trabajo for m in sumadas) else None
            resultados.append(FieldResult(**{**mejor.resultado.to_dict(), "valor": valor}))
    return resultados
