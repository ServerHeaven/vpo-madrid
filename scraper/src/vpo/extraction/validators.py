"""Plausible ranges and cross-field coherence (ARCHITECTURE.md §5.1). No IO.

``es_plausible`` is stricter than data/schema/promocion.schema.json: every value it accepts is
valid there, and implausible or oddly shaped values are rejected rather than repaired.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

from .base import CAMPO_GARAJE, CAMPO_TRASTERO

RENTA_MENSUAL = (150, 2500)
PRECIO_ANEJO = (0, 500)
TASA_ESFUERZO = (0.2, 0.5)
VECES_IPREM = (0, 15)
SUPERFICIE_M2 = (15, 200)
DORMITORIOS = (0, 6)
VIVIENDAS = (1, 5000)
MIEMBROS = (1, 20)
ANIOS_EMPADRONAMIENTO = (0, 20)
EDAD_MIN = (16, 99)
EDAD_MAX = (16, 120)
IPREM_EJERCICIOS_ATRAS, IPREM_EJERCICIOS_ADELANTE = 5, 1
IPREM_EJERCICIO_ESQUEMA = (2015, 2100)
FECHA_ANIOS_ATRAS, FECHA_ANIOS_ADELANTE = 3, 5
MAX_OTRO = 300

NO_EXIGIBLES_EXTRAIDOS = ("empadronamiento", "edad")
# Value of requisitos.no_exigidos -> keys of requisitos.ingresos_por_miembros it also denies.
BORDES_POR_MIEMBROS = {"ingresos_min_iprem": "min_iprem", "ingresos_max_iprem": "max_iprem"}
NO_EXIGIBLES = (
    "ingresos_min_iprem",
    "ingresos_max_iprem",
    "tasa_esfuerzo_max",
    "empadronamiento",
    "edad",
    "no_titular_vivienda",
)

_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_ENTREGA = re.compile(r"[0-9]{4}(-(T[1-4]|0[1-9]|1[0-2]))?")
_INE = re.compile(r"28[0-9]{3}")

_CLAVES_TRAMO = {"miembros_desde", "miembros_hasta", "min_iprem", "max_iprem"}
_CLAVES_EMPADRONAMIENTO = {"ambito", "municipio_ine", "anios_min", "ininterrumpido", "alternativa_trabajo"}
_CLAVES_ANEJO = {"disponibilidad", "precio_mensual_eur"}
_CLAVES_TIPOLOGIA = {
    "dormitorios",
    "superficie_util_m2",
    "renta_mensual_eur",
    "renta_mensual_max_eur",
    "num_viviendas",
    "garaje",
    "trastero",
    "adaptada_pmr",
}


# -- primitives --------------------------------------------------------------------------------


def _numero(valor: Any, rango: tuple[float, float]) -> bool:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return False
    return math.isfinite(valor) and rango[0] <= valor <= rango[1]


def _entero(valor: Any, rango: tuple[int, int]) -> bool:
    return type(valor) is int and rango[0] <= valor <= rango[1]


def _opcional(valor: Any, rango: tuple[float, float], comprobar: Callable[..., bool] = _numero) -> bool:
    return valor is None or comprobar(valor, rango)


def _bool_opcional(valor: Any) -> bool:
    return valor is None or isinstance(valor, bool)


def _objeto(valor: Any, claves: set[str]) -> bool:
    return isinstance(valor, dict) and set(valor) == claves


def _desplazar_anios(fecha: date, anios: int) -> date:
    try:
        return fecha.replace(year=fecha.year + anios)
    except ValueError:  # 29 February
        return fecha.replace(year=fecha.year + anios, day=28)


# -- one check per field -----------------------------------------------------------------------


def _ingresos_min(valor: Any, fecha_ref: date) -> bool:
    return _numero(valor, VECES_IPREM)


def _ingresos_max(valor: Any, fecha_ref: date) -> bool:
    return _numero(valor, VECES_IPREM) and valor > 0


def _tramo(tramo: Any) -> bool:
    if not _objeto(tramo, _CLAVES_TRAMO):
        return False
    desde, hasta = tramo["miembros_desde"], tramo["miembros_hasta"]
    minimo, maximo = tramo["min_iprem"], tramo["max_iprem"]
    if not _entero(desde, MIEMBROS) or not _opcional(hasta, MIEMBROS, _entero):
        return False
    if hasta is not None and hasta < desde:
        return False
    if not _opcional(minimo, VECES_IPREM) or not _opcional(maximo, VECES_IPREM):
        return False
    if minimo is None and maximo is None:
        return False
    if maximo is not None and maximo <= 0:
        return False
    return ingresos_coherentes(minimo, maximo)


def _por_miembros(valor: Any, fecha_ref: date) -> bool:
    if not isinstance(valor, list) or not valor or not all(map(_tramo, valor)):
        return False
    # Sorted and without overlaps; only the last bracket may be open-ended.
    return all(
        a["miembros_hasta"] is not None and a["miembros_hasta"] < b["miembros_desde"]
        for a, b in zip(valor, valor[1:])
    )


def _iprem_pagas(valor: Any, fecha_ref: date) -> bool:
    return type(valor) is int and valor in (12, 14)


def _iprem_ejercicio(valor: Any, fecha_ref: date) -> bool:
    desde, hasta = fecha_ref.year - IPREM_EJERCICIOS_ATRAS, fecha_ref.year + IPREM_EJERCICIOS_ADELANTE
    return _entero(valor, IPREM_EJERCICIO_ESQUEMA) and desde <= valor <= hasta


def _tasa(valor: Any, fecha_ref: date) -> bool:
    return _numero(valor, TASA_ESFUERZO)


def _empadronamiento(valor: Any, fecha_ref: date) -> bool:
    if not _objeto(valor, _CLAVES_EMPADRONAMIENTO) or valor["ambito"] not in ("municipio", "comunidad"):
        return False
    ine = valor["municipio_ine"]
    if ine is not None and not (isinstance(ine, str) and _INE.fullmatch(ine)):
        return False
    if valor["ambito"] == "comunidad" and ine is not None:
        return False
    return (
        _opcional(valor["anios_min"], ANIOS_EMPADRONAMIENTO)
        and _bool_opcional(valor["ininterrumpido"])
        and _bool_opcional(valor["alternativa_trabajo"])
    )


def _edad(valor: Any, fecha_ref: date) -> bool:
    if not _objeto(valor, {"min", "max", "tipo"}) or valor["tipo"] not in ("requisito", "cupo"):
        return False
    minimo, maximo = valor["min"], valor["max"]
    if not _opcional(minimo, EDAD_MIN, _entero) or not _opcional(maximo, EDAD_MAX, _entero):
        return False
    if minimo is None and maximo is None:
        return False
    return minimo is None or maximo is None or minimo <= maximo


def _no_exigido(valor: Any, fecha_ref: date) -> bool:
    return isinstance(valor, str) and valor in NO_EXIGIBLES


def _otro(valor: Any, fecha_ref: date) -> bool:
    return isinstance(valor, str) and bool(valor.strip()) and len(valor) <= MAX_OTRO


def _forma_anejo(valor: Any, disponibilidades: tuple[str, ...]) -> bool:
    if not _objeto(valor, _CLAVES_ANEJO) or valor["disponibilidad"] not in disponibilidades:
        return False
    precio = valor["precio_mensual_eur"]
    if valor["disponibilidad"] == "no" and precio is not None:
        return False
    return _opcional(precio, PRECIO_ANEJO)


def _anejo_global(valor: Any, fecha_ref: date) -> bool:
    return _forma_anejo(valor, ("incluido", "opcional", "no"))


def _tipologia(entrada: Any) -> bool:
    if not _objeto(entrada, _CLAVES_TIPOLOGIA):
        return False
    renta, renta_max = entrada["renta_mensual_eur"], entrada["renta_mensual_max_eur"]
    if not _opcional(renta, RENTA_MENSUAL) or not _opcional(renta_max, RENTA_MENSUAL):
        return False
    if renta_max is not None and (renta is None or renta_max <= renta):
        return False
    if entrada["dormitorios"] is None and entrada["superficie_util_m2"] is None and renta is None:
        return False  # describes nothing
    disponibilidades = ("incluido", "opcional", "no", "desconocido")
    return (
        _opcional(entrada["dormitorios"], DORMITORIOS, _entero)
        and _opcional(entrada["superficie_util_m2"], SUPERFICIE_M2)
        and _opcional(entrada["num_viviendas"], VIVIENDAS, _entero)
        and _forma_anejo(entrada["garaje"], disponibilidades)
        and _forma_anejo(entrada["trastero"], disponibilidades)
        and _bool_opcional(entrada["adaptada_pmr"])
    )


def _tipologias(valor: Any, fecha_ref: date) -> bool:
    return isinstance(valor, list) and bool(valor) and all(map(_tipologia, valor))


def _fecha(valor: Any, fecha_ref: date) -> bool:
    if not isinstance(valor, str) or not _FECHA.fullmatch(valor):
        return False
    try:
        fecha = date.fromisoformat(valor)
    except ValueError:
        return False
    desde = _desplazar_anios(fecha_ref, -FECHA_ANIOS_ATRAS)
    return desde <= fecha <= _desplazar_anios(fecha_ref, FECHA_ANIOS_ADELANTE)


def _entrega(valor: Any, fecha_ref: date) -> bool:
    if not isinstance(valor, str) or not _ENTREGA.fullmatch(valor):
        return False
    return fecha_ref.year - FECHA_ANIOS_ATRAS <= int(valor[:4]) <= fecha_ref.year + FECHA_ANIOS_ADELANTE


_VALIDADORES: dict[str, Callable[[Any, date], bool]] = {
    "/requisitos/ingresos_min_iprem": _ingresos_min,
    "/requisitos/ingresos_max_iprem": _ingresos_max,
    "/requisitos/ingresos_por_miembros": _por_miembros,
    "/requisitos/iprem_pagas": _iprem_pagas,
    "/requisitos/iprem_ejercicio": _iprem_ejercicio,
    "/requisitos/tasa_esfuerzo_max": _tasa,
    "/requisitos/empadronamiento": _empadronamiento,
    "/requisitos/edad": _edad,
    "/requisitos/no_exigidos": _no_exigido,
    "/requisitos/otros": _otro,
    "/tipologias": _tipologias,
    CAMPO_GARAJE: _anejo_global,
    CAMPO_TRASTERO: _anejo_global,
    "/fechas/inscripcion_inicio": _fecha,
    "/fechas/inscripcion_fin": _fecha,
    "/fechas/sorteo": _fecha,
    "/fechas/entrega_prevista": _entrega,
}
CAMPOS_SOPORTADOS = frozenset(_VALIDADORES)


def es_plausible(campo: str, valor: Any, fecha_ref: date) -> bool:
    """False for an unsupported field, a wrong shape or a value outside its plausible range."""
    comprobar = _VALIDADORES.get(campo)
    return comprobar is not None and comprobar(valor, fecha_ref)


# -- cross-field coherence ---------------------------------------------------------------------


def ingresos_coherentes(minimo: float | None, maximo: float | None) -> bool:
    return minimo is None or maximo is None or minimo < maximo


def fechas_coherentes(inicio: str | None, fin: str | None) -> bool:
    """Both ISO dates, which sort as text."""
    return inicio is None or fin is None or inicio <= fin


def rentas_coherentes(tipologias: Sequence[dict[str, Any]]) -> bool:
    """The cheapest 3-bedroom rent is not below the cheapest 1-bedroom rent."""

    def minima(dormitorios: int) -> float | None:
        rentas = [
            t["renta_mensual_eur"]
            for t in tipologias
            if t["dormitorios"] == dormitorios and t["renta_mensual_eur"] is not None
        ]
        return min(rentas, default=None)

    una, tres = minima(1), minima(3)
    return una is None or tres is None or tres >= una


def tramos_compatibles(tramos: Sequence[dict[str, Any]], clave: str, valor: float | None) -> bool:
    """Can a flat ``valor`` coexist with a per-members table? ``clave`` is min_iprem or max_iprem."""
    return valor is None or all(t[clave] is None or t[clave] == valor for t in tramos)
