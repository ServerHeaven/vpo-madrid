"""Merges accepted PDF results into what the HTML gave (ARCHITECTURE.md §5.1). No IO.

Priority: structured HTML > PDF table > PDF text (the last two are settled by the pipeline).
A value that is already there is never overwritten: PDF results only fill unknowns. Every value
taken from a PDF gets its own ``procedencia`` entry. Anything that cannot be placed without
guessing stays null and is returned as a "conflicto".
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from typing import Any

from . import validators
from .base import (
    CAMPO_GARAJE,
    CAMPO_TRASTERO,
    MAX_EVIDENCIA,
    Descarte,
    ExtractionResult,
    FieldResult,
    plegar,
)

TOLERANCIA_SUPERFICIE_M2 = 0.5  # HTML pages round the useful area

_REQUISITOS_SIMPLES = (
    "ingresos_min_iprem",
    "ingresos_max_iprem",
    "iprem_pagas",
    "iprem_ejercicio",
    "tasa_esfuerzo_max",
    "empadronamiento",
    "edad",
)
_FECHAS = ("inscripcion_inicio", "inscripcion_fin", "sorteo", "entrega_prevista")
_ANEJOS = {CAMPO_GARAJE: "garaje", CAMPO_TRASTERO: "trastero"}

Procedencias = dict[str, dict[str, Any]]
Conflictos = dict[str, list[FieldResult]]
# (index of the tipologia, "garaje"|"trastero") -> what the merged PDF rows said about it
Anejos = dict[tuple[int, str], list[dict[str, Any]]]


def aplicar(datos: dict, procedencia: dict, resultado: ExtractionResult) -> tuple[dict, dict, list[Descarte]]:
    """Copies of ``datos`` and ``procedencia`` completed with ``resultado``.

    The returned discards are only the ones found while merging, not those in ``resultado``.
    """
    datos, procedencia = copy.deepcopy(datos), copy.deepcopy(procedencia)
    conflictos: Conflictos = {}
    aceptados: dict[str, list[FieldResult]] = {}
    for result in resultado.campos:
        aceptados.setdefault(result.campo, []).append(result)

    # The per-members table goes first: it decides which flat values can still be added.
    _por_miembros(datos["requisitos"], procedencia, aceptados, conflictos)
    _requisitos(datos["requisitos"], procedencia, aceptados, conflictos)
    _fechas(datos["fechas"], procedencia, aceptados, conflictos)
    _no_exigidos(datos["requisitos"], procedencia, aceptados)
    _otros(datos["requisitos"], procedencia, aceptados)
    filas = _tipologias(datos, procedencia, aceptados, conflictos)
    _anejos(datos["tipologias"], procedencia, aceptados, filas)

    descartes = [Descarte(campo, "conflicto", tuple(conflictos[campo])) for campo in sorted(conflictos)]
    return datos, procedencia, descartes


def _entrada(result: FieldResult) -> dict[str, Any]:
    return {
        "metodo": result.metodo,
        "confianza": min(max(result.confianza, 0.0), 1.0),
        "documento": result.documento,
        "pagina": result.pagina if result.pagina and result.pagina >= 1 else None,
        "evidencia": result.evidencia[:MAX_EVIDENCIA] or None,
        "regla": result.regla or None,
    }


def _anotar_conflicto(conflictos: Conflictos, campo: str, result: FieldResult) -> None:
    conflictos.setdefault(campo, []).append(result)


# -- requisitos and fechas ---------------------------------------------------------------------


def _por_miembros(requisitos, procedencia: Procedencias, aceptados, conflictos: Conflictos) -> None:
    campo = "/requisitos/ingresos_por_miembros"
    for result in aceptados.get(campo, ()):
        if requisitos["ingresos_por_miembros"] is not None:
            continue
        contradice = any(
            not validators.tramos_compatibles(result.valor, borde, requisitos[nombre])
            or (nombre in requisitos["no_exigidos"] and any(t[borde] is not None for t in result.valor))
            for nombre, borde in validators.BORDES_POR_MIEMBROS.items()
        )
        if contradice:
            _anotar_conflicto(conflictos, campo, result)
            continue
        requisitos["ingresos_por_miembros"] = copy.deepcopy(result.valor)
        procedencia[campo] = _entrada(result)


def _requisitos(requisitos, procedencia: Procedencias, aceptados, conflictos: Conflictos) -> None:
    for nombre in _REQUISITOS_SIMPLES:
        campo = f"/requisitos/{nombre}"
        for result in aceptados.get(campo, ()):
            if requisitos[nombre] is not None:
                continue
            if nombre in requisitos["no_exigidos"] or not _encaja_ingresos(requisitos, nombre, result.valor):
                _anotar_conflicto(conflictos, campo, result)
                continue
            requisitos[nombre] = copy.deepcopy(result.valor)
            procedencia[campo] = _entrada(result)


def _encaja_ingresos(requisitos, nombre: str, valor: Any) -> bool:
    """A flat income bound must agree with the other bound and with the per-members table."""
    borde = validators.BORDES_POR_MIEMBROS.get(nombre)
    if borde is None:
        return True
    tramos = requisitos["ingresos_por_miembros"]
    if tramos is not None and not validators.tramos_compatibles(tramos, borde, valor):
        return False
    if borde == "min_iprem":
        return validators.ingresos_coherentes(valor, requisitos["ingresos_max_iprem"])
    return validators.ingresos_coherentes(requisitos["ingresos_min_iprem"], valor)


def _fechas(fechas, procedencia: Procedencias, aceptados, conflictos: Conflictos) -> None:
    for nombre in _FECHAS:
        campo = f"/fechas/{nombre}"
        for result in aceptados.get(campo, ()):
            if fechas[nombre] is not None:
                continue
            nuevas = fechas | {nombre: result.valor}
            if nombre.startswith("inscripcion_") and not validators.fechas_coherentes(
                nuevas["inscripcion_inicio"], nuevas["inscripcion_fin"]
            ):
                _anotar_conflicto(conflictos, campo, result)
                continue
            fechas[nombre] = result.valor
            procedencia[campo] = _entrada(result)


def _puntero_de_elemento(procedencia: Procedencias, base: str, indice: int) -> str:
    """The list's own pointer when the PDF starts the list; the item's pointer when it adds to it."""
    return base if indice == 0 and base not in procedencia else f"{base}/{indice}"


def _no_exigidos(requisitos, procedencia: Procedencias, aceptados) -> None:
    campo = "/requisitos/no_exigidos"
    lista = requisitos["no_exigidos"]
    for result in aceptados.get(campo, ()):
        nombre = result.valor
        if nombre in lista or requisitos[nombre] is not None:
            continue  # a value that is there outranks the PDF's negation
        borde = validators.BORDES_POR_MIEMBROS.get(nombre)
        tramos = requisitos["ingresos_por_miembros"]
        if borde and tramos and any(t[borde] is not None for t in tramos):
            continue
        procedencia[_puntero_de_elemento(procedencia, campo, len(lista))] = _entrada(result)
        lista.append(nombre)


def _frase(texto: str) -> str:
    return " ".join(plegar(texto).split()).rstrip(" .")


def _otros(requisitos, procedencia: Procedencias, aceptados) -> None:
    campo = "/requisitos/otros"
    lista = requisitos["otros"]
    vistos = {_frase(texto) for texto in lista}
    for result in aceptados.get(campo, ()):
        if _frase(result.valor) in vistos:
            continue
        vistos.add(_frase(result.valor))
        procedencia[_puntero_de_elemento(procedencia, campo, len(lista))] = _entrada(result)
        lista.append(result.valor)


# -- tipologias --------------------------------------------------------------------------------


def _tipologias(datos, procedencia: Procedencias, aceptados, conflictos: Conflictos) -> Anejos:
    """Take the PDF list when the HTML has none; otherwise complete the HTML list by dormitorios."""
    campo = "/tipologias"
    filas_anejos: Anejos = {}
    for result in aceptados.get(campo, ()):
        existentes = datos["tipologias"]
        if not existentes:
            datos["tipologias"] = copy.deepcopy(result.valor)
            procedencia[campo] = _entrada(result)
            continue
        conocidos = {t["dormitorios"] for t in existentes} - {None}
        if any(fila["dormitorios"] not in conocidos for fila in result.valor):
            # The PDF may describe something else: attach nothing.
            _anotar_conflicto(conflictos, campo, result)
            continue
        ambiguo = False
        for dormitorios in sorted({fila["dormitorios"] for fila in result.valor}):
            indices = [i for i, t in enumerate(existentes) if t["dormitorios"] == dormitorios]
            filas = [fila for fila in result.valor if fila["dormitorios"] == dormitorios]
            if len(indices) != 1 or not _compatibles(existentes[indices[0]], filas):
                ambiguo = True
                continue
            indice = indices[0]
            for nombre in _ANEJOS.values():
                filas_anejos[indice, nombre] = [
                    fila[nombre] for fila in filas if fila[nombre]["disponibilidad"] != "desconocido"
                ]
            for clave in _completar(existentes[indice], filas):
                procedencia[f"{campo}/{indice}/{clave}"] = _entrada(result)
        if ambiguo:
            _anotar_conflicto(conflictos, campo, result)
    return filas_anejos


def _compatibles(existente: dict, filas: Sequence[dict]) -> bool:
    """Nothing the HTML states about this typology contradicts the PDF rows."""
    superficie = existente["superficie_util_m2"]
    if superficie is not None and any(
        fila["superficie_util_m2"] is not None
        and abs(fila["superficie_util_m2"] - superficie) > TOLERANCIA_SUPERFICIE_M2
        for fila in filas
    ):
        return False
    total = existente["num_viviendas"]
    unidades = [fila["num_viviendas"] for fila in filas]
    return total is None or None in unidades or sum(unidades) == total


def _comun(filas: Sequence[dict], clave: str) -> Any:
    """The value every row shares, or None."""
    primero = filas[0][clave]
    return copy.deepcopy(primero) if all(fila[clave] == primero for fila in filas) else None


def _completar(existente: dict, filas: Sequence[dict]) -> list[str]:
    """Fill the unknowns of ``existente`` from rows with its dormitorios. Returns the keys filled."""
    llenas: list[str] = []

    rentas = [fila["renta_mensual_eur"] for fila in filas]
    # The pair is atomic, and a row without rent would make the range incomplete.
    par = (existente["renta_mensual_eur"], existente["renta_mensual_max_eur"])
    if par == (None, None) and None not in rentas:
        minima = min(rentas)
        maxima = max(fila["renta_mensual_max_eur"] or fila["renta_mensual_eur"] for fila in filas)
        existente["renta_mensual_eur"] = minima
        llenas.append("renta_mensual_eur")
        if maxima > minima:
            existente["renta_mensual_max_eur"] = maxima
            llenas.append("renta_mensual_max_eur")

    unidades = [fila["num_viviendas"] for fila in filas]
    nuevos = {
        "superficie_util_m2": _comun(filas, "superficie_util_m2"),
        "num_viviendas": None if None in unidades else sum(unidades),
        "adaptada_pmr": _comun(filas, "adaptada_pmr"),
    }
    for clave, valor in nuevos.items():
        if existente[clave] is None and valor is not None:
            existente[clave] = valor
            llenas.append(clave)

    for nombre in _ANEJOS.values():
        comun = _comun(filas, nombre)
        if comun is None or comun["disponibilidad"] == "desconocido":
            continue
        unido = _unir_anejo(existente[nombre], comun)
        if unido is not None:
            existente[nombre] = unido
            llenas.append(nombre)
    return llenas


def _unir_anejo(actual: dict, nuevo: dict) -> dict | None:
    """``nuevo`` placed on an annex of unknown availability, or None if it does not fit."""
    if actual["disponibilidad"] != "desconocido":
        return None
    precio, propuesto = actual["precio_mensual_eur"], nuevo["precio_mensual_eur"]
    if precio is not None:
        if nuevo["disponibilidad"] == "no" or (propuesto is not None and propuesto != precio):
            return None
        propuesto = precio
    return {"disponibilidad": nuevo["disponibilidad"], "precio_mensual_eur": propuesto}


def _anejos(tipologias: list[dict], procedencia: Procedencias, aceptados, filas: Anejos) -> None:
    """A garage or storage room stated for the whole promotion fills the typologies that lack it."""
    for campo, nombre in _ANEJOS.items():
        for result in aceptados.get(campo, ()):
            for indice, tipologia in enumerate(tipologias):
                if not all(_concuerda(fila, result.valor) for fila in filas.get((indice, nombre), ())):
                    continue
                unido = _unir_anejo(tipologia[nombre], result.valor)
                if unido is not None:
                    tipologia[nombre] = unido
                    procedencia[f"/tipologias/{indice}/{nombre}"] = _entrada(result)


def _concuerda(fila: dict, general: dict) -> bool:
    precios = {fila["precio_mensual_eur"], general["precio_mensual_eur"]} - {None}
    return fila["disponibilidad"] == general["disponibilidad"] and len(precios) <= 1
