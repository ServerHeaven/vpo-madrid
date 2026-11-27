from datetime import date

import pytest
from conftest import DATA_DIR

from vpo.core.normalize import Municipios
from vpo.extraction.base import CAMPO_GARAJE, CAMPO_TRASTERO, Document, ExtractionContext, FieldResult
from vpo.extraction.rules.anejos import AnejosExtractor

CTX = ExtractionContext("demo", date(2026, 11, 27), Municipios.load(DATA_DIR))


def run(*parrafos: str, **kwargs) -> list[FieldResult]:
    return AnejosExtractor().extract(Document.desde_parrafos([list(parrafos)], **kwargs), CTX)


def valores(*parrafos: str) -> dict[str, list[tuple]]:
    found: dict[str, list[tuple]] = {}
    for r in run(*parrafos):
        found.setdefault(r.campo, []).append((r.valor["disponibilidad"], r.valor["precio_mensual_eur"]))
    return found


def ambos(disponibilidad: str, precio=None) -> dict:
    return {CAMPO_GARAJE: [(disponibilidad, precio)], CAMPO_TRASTERO: [(disponibilidad, precio)]}


@pytest.mark.parametrize(
    "frase",
    [
        "Las viviendas tienen plaza de garaje y trastero incluidos en la renta.",
        "La renta incluye plaza de garaje y trastero.",
        "Viviendas con garaje y trastero vinculados.",
        "La plaza de garaje y el trastero son anejos inseparables de la vivienda.",
    ],
)
def test_included(frase):
    assert valores(frase) == ambos("incluido")


@pytest.mark.parametrize(
    "frase",
    [
        "La plaza de garaje es opcional.",
        "Plaza de garaje no vinculada.",
        "La plaza de garaje podrá alquilarse por separado.",
        "De forma opcional, plaza de garaje.",
    ],
)
def test_optional(frase):
    assert valores(frase) == {CAMPO_GARAJE: [("opcional", None)]}


def test_explicit_negation_is_the_only_way_to_no():
    assert valores("La promoción no dispone de trastero.") == {CAMPO_TRASTERO: [("no", None)]}
    assert valores("Edificio sin garaje.") == {CAMPO_GARAJE: [("no", None)]}


def test_monthly_price_before_or_after_the_annex():
    assert valores("Plaza de garaje: 60 euros al mes.") == {CAMPO_GARAJE: [("desconocido", 60.0)]}
    assert valores("Alquiler de 15,50 €/mes por trastero.") == {CAMPO_TRASTERO: [("desconocido", 15.5)]}


def test_compatible_statements_are_one_candidate():
    results = run("La plaza de garaje es opcional.", "El alquiler del garaje es de 55 euros mensuales.")
    (result,) = results
    assert result.valor == {"disponibilidad": "opcional", "precio_mensual_eur": 55.0}
    assert (result.regla, result.metodo, result.pagina) == ("REG-ANEJO-02", "pdf_texto", 1)


def test_contradictions_give_two_candidates():
    found = valores("La plaza de garaje es opcional.", "La renta incluye plaza de garaje.")
    assert sorted(found[CAMPO_GARAJE]) == [("incluido", None), ("opcional", None)]
    found = valores("Garaje: 50 euros al mes.", "Garaje: 70 euros al mes.")
    assert found[CAMPO_GARAJE] == [("desconocido", 50.0), ("desconocido", 70.0)]


def test_legal_quotes_have_low_confidence():
    (result,) = run("La plaza de garaje es opcional.", normativo=True)
    assert result.confianza == 0.55


@pytest.mark.parametrize(
    "frase",
    [
        "Se valorará la documentación sobre garaje.",
        "La promoción cuenta con 120 plazas de garaje.",
        "Garaje: 60 euros al mes, IVA incluido.".replace("60 euros al mes", "consultar"),
        "En su caso, garaje y trastero vinculados.",
        "Algunas viviendas tienen trastero incluido.",
        "La renta no incluye plaza de garaje.",
        "La plaza de garaje no está incluida en la renta.",
        "No podrán acceder las personas que no dispongan de garaje.",
        "Precio de venta de la vivienda con garaje y trastero anejos.",
        "Aparcamiento de bicicletas incluido.",
        "Vivienda de 2 dormitorios con plaza de garaje por 200 euros al mes.",
        "La fianza del garaje es de 60 euros al mes.",
        "Plaza de garaje: 12.000 euros.",
        "Garaje y trastero: 80 euros al mes.",
    ],
)
def test_nothing_is_guessed(frase):
    assert valores(frase) == {}
