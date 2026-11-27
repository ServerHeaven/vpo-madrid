"""Plausible ranges and coherence checks. Values are synthetic."""

from datetime import date

import pytest

from conftest import build_promo, validate_promo
from vpo.extraction import validators
from vpo.extraction.base import CAMPO_GARAJE, CAMPO_TRASTERO

REF = date(2026, 11, 27)
EMPADRONAMIENTO = {
    "ambito": "municipio",
    "municipio_ine": "28079",
    "anios_min": 3,
    "ininterrumpido": True,
    "alternativa_trabajo": None,
}
TRAMO = {"miembros_desde": 1, "miembros_hasta": 2, "min_iprem": 2.5, "max_iprem": 5.5}


def anejo(disponibilidad="desconocido", precio=None):
    return {"disponibilidad": disponibilidad, "precio_mensual_eur": precio}


def tipologia(dormitorios=2, renta=600.0, **changes):
    return {
        "dormitorios": dormitorios,
        "superficie_util_m2": 60.0,
        "renta_mensual_eur": renta,
        "renta_mensual_max_eur": None,
        "num_viviendas": 10,
        "garaje": anejo(),
        "trastero": anejo(),
        "adaptada_pmr": None,
    } | changes


PLAUSIBLES = [
    ("/requisitos/ingresos_min_iprem", 0),
    ("/requisitos/ingresos_min_iprem", 2.5),
    ("/requisitos/ingresos_max_iprem", 15),
    ("/requisitos/ingresos_por_miembros", [TRAMO, TRAMO | {"miembros_desde": 3, "miembros_hasta": None}]),
    ("/requisitos/iprem_pagas", 12),
    ("/requisitos/iprem_pagas", 14),
    ("/requisitos/iprem_ejercicio", 2025),
    ("/requisitos/tasa_esfuerzo_max", 0.2),
    ("/requisitos/tasa_esfuerzo_max", 0.5),
    ("/requisitos/empadronamiento", EMPADRONAMIENTO),
    ("/requisitos/empadronamiento", EMPADRONAMIENTO | {"ambito": "comunidad", "municipio_ine": None}),
    ("/requisitos/edad", {"min": None, "max": 34, "tipo": "cupo"}),
    ("/requisitos/no_exigidos", "empadronamiento"),
    ("/requisitos/otros", "IVA no incluido"),
    ("/tipologias", [tipologia(renta=150), tipologia(3, 2500)]),
    ("/tipologias", [tipologia(renta=500, renta_mensual_max_eur=600)]),
    (CAMPO_GARAJE, anejo("opcional", 50)),
    (CAMPO_TRASTERO, anejo("no")),
    ("/fechas/inscripcion_inicio", "2023-11-27"),
    ("/fechas/inscripcion_fin", "2031-11-27"),
    ("/fechas/sorteo", "2026-12-01"),
    ("/fechas/entrega_prevista", "2027"),
    ("/fechas/entrega_prevista", "2027-T2"),
    ("/fechas/entrega_prevista", "2027-06"),
]

IMPLAUSIBLES = [
    ("/requisitos/ingresos_min_iprem", -1),
    ("/requisitos/ingresos_min_iprem", True),
    ("/requisitos/ingresos_min_iprem", float("nan")),
    ("/requisitos/ingresos_max_iprem", 0),
    ("/requisitos/ingresos_max_iprem", 15.5),
    ("/requisitos/ingresos_max_iprem", "5,5"),
    ("/requisitos/ingresos_por_miembros", []),
    ("/requisitos/ingresos_por_miembros", [TRAMO | {"min_iprem": 6}]),
    ("/requisitos/ingresos_por_miembros", [TRAMO | {"min_iprem": None, "max_iprem": None}]),
    ("/requisitos/ingresos_por_miembros", [TRAMO, TRAMO]),  # overlapping brackets
    ("/requisitos/ingresos_por_miembros", [TRAMO | {"miembros_hasta": 0}]),
    ("/requisitos/iprem_pagas", 13),
    ("/requisitos/iprem_pagas", 12.0),
    ("/requisitos/iprem_ejercicio", 2014),
    ("/requisitos/iprem_ejercicio", 2031),
    ("/requisitos/tasa_esfuerzo_max", 0.19),
    ("/requisitos/tasa_esfuerzo_max", 35),
    ("/requisitos/empadronamiento", EMPADRONAMIENTO | {"anios_min": 21}),
    ("/requisitos/empadronamiento", EMPADRONAMIENTO | {"municipio_ine": "08019"}),
    ("/requisitos/empadronamiento", EMPADRONAMIENTO | {"ambito": "comunidad"}),
    ("/requisitos/empadronamiento", {"ambito": "municipio"}),
    ("/requisitos/edad", {"min": None, "max": None, "tipo": "requisito"}),
    ("/requisitos/edad", {"min": 40, "max": 30, "tipo": "requisito"}),
    ("/requisitos/edad", {"min": 10, "max": None, "tipo": "requisito"}),
    ("/requisitos/no_exigidos", "nacionalidad"),
    ("/requisitos/otros", "x" * 301),
    ("/requisitos/otros", "  "),
    ("/tipologias", []),
    ("/tipologias", [tipologia(renta=149)]),
    ("/tipologias", [tipologia(), tipologia(renta=2501)]),
    ("/tipologias", [tipologia(renta=600, renta_mensual_max_eur=600)]),
    ("/tipologias", [tipologia(renta=None, renta_mensual_max_eur=600)]),
    ("/tipologias", [tipologia(7)]),
    ("/tipologias", [tipologia(superficie_util_m2=10)]),
    ("/tipologias", [tipologia(num_viviendas=0)]),
    ("/tipologias", [tipologia(None, None, superficie_util_m2=None)]),
    ("/tipologias", [{"dormitorios": 2}]),
    (CAMPO_GARAJE, anejo()),
    (CAMPO_GARAJE, anejo("no", 40)),
    (CAMPO_GARAJE, anejo("opcional", 900)),
    ("/fechas/sorteo", "2023-11-26"),
    ("/fechas/sorteo", "2031-11-28"),
    ("/fechas/sorteo", "2027-02-30"),
    ("/fechas/sorteo", "20270201"),
    ("/fechas/entrega_prevista", "2040"),
    ("/fechas/entrega_prevista", "2027-T5"),
    ("/requisitos/no_titular_vivienda", True),  # not extracted in Phase 3
]


@pytest.mark.parametrize(("campo", "valor"), PLAUSIBLES)
def test_plausible_values_are_accepted_and_fit_the_schema(campo, valor):
    assert validators.es_plausible(campo, valor, REF)

    promo = build_promo()
    parts = campo.strip("/").split("/")
    if campo in (CAMPO_GARAJE, CAMPO_TRASTERO):
        promo["tipologias"][0][parts[-1]] = valor
    elif campo in ("/requisitos/no_exigidos", "/requisitos/otros"):
        promo["requisitos"][parts[-1]] = [valor]
    elif len(parts) == 1:
        promo[parts[0]] = valor
    else:
        promo[parts[0]][parts[1]] = valor
    assert validate_promo(promo) == []


@pytest.mark.parametrize(("campo", "valor"), IMPLAUSIBLES)
def test_implausible_values_are_rejected(campo, valor):
    assert not validators.es_plausible(campo, valor, REF)


def test_date_window_on_29_february():
    assert validators.es_plausible("/fechas/sorteo", "2025-02-28", date(2028, 2, 29))
    assert not validators.es_plausible("/fechas/sorteo", "2025-02-27", date(2028, 2, 29))


def test_coherence_helpers():
    assert validators.ingresos_coherentes(2.5, 5.5)
    assert validators.ingresos_coherentes(None, 5.5)
    assert not validators.ingresos_coherentes(5.5, 5.5)
    assert validators.fechas_coherentes("2026-12-01", "2026-12-01")
    assert not validators.fechas_coherentes("2026-12-02", "2026-12-01")
    assert validators.rentas_coherentes([tipologia(1, 500), tipologia(3, 500)])
    assert validators.rentas_coherentes([tipologia(1, 500), tipologia(2, 400)])
    assert not validators.rentas_coherentes([tipologia(1, 500), tipologia(3, 499)])
    assert validators.tramos_compatibles([TRAMO], "max_iprem", 5.5)
    assert not validators.tramos_compatibles([TRAMO], "max_iprem", 7.5)
