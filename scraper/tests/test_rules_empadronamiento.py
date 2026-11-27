"""Residency rules on standalone Spanish sentences. The sentences are synthetic."""

from datetime import date

import pytest
from conftest import DATA_DIR

from vpo.core.normalize import Municipios
from vpo.extraction.base import Document, ExtractionContext
from vpo.extraction.rules.empadronamiento import EmpadronamientoExtractor

MUNICIPIOS = Municipios.load(DATA_DIR)
MADRID = "28079"
GETAFE = "28065"
CAMPO = "/requisitos/empadronamiento"


def extract(*parrafos: str, municipio: str | None = GETAFE, **kwargs):
    ctx = ExtractionContext(
        fuente_id="demo", fecha_ref=date(2026, 11, 27), municipios=MUNICIPIOS, municipio_ine=municipio
    )
    return EmpadronamientoExtractor().extract(Document.desde_parrafos([list(parrafos)], **kwargs), ctx)


def emp(ine=MADRID, anios=None, ininterrumpido=None, trabajo=None) -> dict:
    return {
        "ambito": "municipio" if ine else "comunidad",
        "municipio_ine": ine,
        "anios_min": anios,
        "ininterrumpido": ininterrumpido,
        "alternativa_trabajo": trabajo,
    }


def values(*parrafos: str, **kwargs) -> list:
    return [r.valor for r in extract(*parrafos, **kwargs) if r.campo == CAMPO]


@pytest.mark.parametrize(
    "frase, valor",
    [
        ("Estar empadronado en el municipio de Madrid con una antigüedad mínima de 3 años.", emp(anios=3)),
        ("Estar empadronados en Madrid durante al menos tres años.", emp(anios=3)),
        ("Deberán estar empadronados en el municipio de Getafe al menos 5 años.", emp(GETAFE, 5)),
        ("Estar empadronado/a en el municipio con una antigüedad de un año.", emp(GETAFE, 1)),
        ("Acreditar un periodo mínimo de empadronamiento en Getafe de dos (2) años.", emp(GETAFE, 2)),
        ("Estar empadronado en Getafe con 3 años de antigüedad.", emp(GETAFE, 3)),
        ("Estar empadronado en Getafe con una antigüedad mínima de 6 meses.", emp(GETAFE, 0.5)),
        ("Estar empadronado en el municipio de Pozuelo de Alarcón.", emp("28115")),
        ("Podrán solicitar la vivienda los empadronados en este municipio.", emp(GETAFE)),
        (
            "Figurar inscrito en el Padrón Municipal de Habitantes de Madrid con una antigüedad de 3 años.",
            emp(anios=3),
        ),
    ],
)
def test_municipality(frase, valor):
    results = extract(frase)
    assert [r.valor for r in results] == [valor]
    assert results[0].regla == "REG-EMP-01"
    assert results[0].evidencia == frase


@pytest.mark.parametrize(
    "frase",
    [
        "Estar empadronado en Madrid de forma ininterrumpida durante al menos 3 años.",
        "Estar empadronado en Madrid con una antigüedad mínima de 3 años de manera continuada.",
        "Estar empadronado en Madrid durante los 3 años inmediatamente anteriores a la solicitud.",
    ],
)
def test_uninterrupted(frase):
    assert values(frase) == [emp(anios=3, ininterrumpido=True)]


@pytest.mark.parametrize(
    "frase",
    [
        "Estar empadronado o trabajar en el municipio de Madrid.",
        "Estar empadronado en el municipio de Madrid o desarrollar su actividad laboral en el mismo.",
        "Estar empadronado en Madrid o, en su defecto, tener su puesto de trabajo en dicho municipio.",
        "Trabajar en el municipio de Madrid o estar empadronado en él.",
    ],
)
def test_work_alternative(frase):
    assert values(frase) == [emp(trabajo=True)]


@pytest.mark.parametrize(
    "frase",
    [
        "Estar empadronado en la Comunidad de Madrid.",
        "Estar empadronado en cualquier municipio de la Comunidad de Madrid.",
        "Deberán estar empadronados en un municipio de la Comunidad de Madrid.",
    ],
)
def test_region(frase):
    results = extract(frase)
    assert [(r.valor, r.regla) for r in results] == [(emp(None), "REG-EMP-04")]


def test_unnamed_municipality_without_context_is_not_guessed():
    assert values("Estar empadronado en el municipio.", municipio=None) == []


def test_following_requirements_do_not_lend_their_years():
    frase = (
        "Estar empadronado en Madrid y no haber sido adjudicatario de vivienda protegida durante los "
        "últimos 5 años."
    )
    assert values(frase) == [emp()]


@pytest.mark.parametrize(
    "frase",
    [
        "Tendrán preferencia los empadronados en Madrid con una antigüedad de 3 años.",
        "Por cada año empadronado en Madrid: 2 puntos.",
        "Se establece un cupo para empadronados en Getafe.",
        "El 30 % de las viviendas se destinará a personas empadronadas en Getafe.",
        "Certificado de empadronamiento en el municipio de Madrid.",
        "Deberá aportar volante de empadronamiento de todos los miembros.",
        "Certificado de las personas empadronadas en el domicilio actual en Madrid.",
        "La persona adjudicataria deberá estar empadronada en la vivienda adjudicada en Madrid.",
        "Estar empadronado en el municipio de Villanueva del Trabuco.",
        "Estar empadronado en Toledo.",
        "Estar empadronado con una antigüedad mínima de 3 años.",
        "Estar empadronado en Getafe o en la Comunidad de Madrid.",
        "Estar empadronado en Getafe o trabajar en Madrid.",
        "Estar empadronado en Madrid al menos 3 años dentro de los últimos 5 años.",
        "El empadronamiento en Madrid se comprobará de oficio.",
    ],
)
def test_not_a_requirement(frase):
    assert extract(frase) == []


def test_priority_heading_discards_its_list():
    assert extract("Criterios de prioridad:", "a) Estar empadronado en Madrid.") == []


def test_mentions_with_more_or_less_detail_are_merged():
    assert values(
        "Estar empadronado en el municipio de Madrid.",
        "Estar empadronado en Madrid con una antigüedad mínima de 3 años.",
        "El solicitante deberá estar empadronado en Madrid de forma ininterrumpida o trabajar en Madrid.",
    ) == [emp(anios=3, ininterrumpido=True, trabajo=True)]


def test_different_years_stay_apart():
    assert values(
        "Estar empadronado en Madrid con una antigüedad mínima de 3 años.",
        "Estar empadronado en Madrid con una antigüedad mínima de 5 años.",
        "Estar empadronado en Madrid.",
    ) == [emp(anios=3), emp(anios=5)]


def test_continuity_stated_next_to_a_distant_figure():
    frase = (
        "Estar empadronado en el municipio de Majadahonda a fecha de inicio del plazo de presentación de "
        "solicitudes, habiéndolo estado, además, durante los últimos 10 años ininterrumpidos."
    )
    assert values(frase) == [emp("28080", 10, ininterrumpido=True)]


def test_two_alternative_seniorities_are_both_emitted():
    frase = (
        "Estar empadronado en el municipio de Madrid con una antigüedad mínima de 5 años ininterrumpidamente "
        "o 8 años dentro de los últimos 10 años."
    )
    assert values(frase) == [emp(anios=5, ininterrumpido=True), emp(anios=8)]


def test_hyphenated_name_and_work_alternative():
    frase = (
        "Estar empadronado en el municipio de Rivas Vaciamadrid durante diez años (consecutivos o no) o "
        "desempeñar su actividad laboral en un centro de trabajo ubicado en el mismo."
    )
    assert values(frase) == [emp("28123", 10, trabajo=True)]


def test_different_places_stay_apart():
    assert values("Estar empadronado en Madrid.", "Estar empadronado en la Comunidad de Madrid.") == [
        emp(),
        emp(None),
    ]


@pytest.mark.parametrize(
    "frase",
    [
        "No se exige estar empadronado en el municipio.",
        "No es necesario el empadronamiento.",
        "No se requiere empadronamiento para participar.",
        "Podrá solicitarse sin necesidad de estar empadronado.",
        "El empadronamiento no es requisito.",
    ],
)
def test_explicitly_not_required(frase):
    results = extract(frase)
    assert [(r.campo, r.valor, r.regla) for r in results] == [
        ("/requisitos/no_exigidos", "empadronamiento", "REG-EMP-05")
    ]


@pytest.mark.parametrize(
    "frase",
    [
        "No se exige antigüedad mínima de empadronamiento.",
        "No es necesario estar empadronado en Madrid, bastando con residir en la región.",
        "No es necesario estar empadronado si se trabaja en el municipio.",
        "No será necesario aportar el certificado de empadronamiento.",
    ],
)
def test_qualified_negation_is_not_a_negation(frase):
    assert [r for r in extract(frase) if r.campo == "/requisitos/no_exigidos"] == []


def test_confidence():
    frase = "Estar empadronado en Madrid con una antigüedad mínima de 3 años."
    assert extract(frase)[0].confianza == 0.85
    assert extract(frase, seccion="requisitos")[0].confianza == 0.95
    assert extract(frase, normativo=True)[0].confianza == 0.55


def test_no_less_than_is_not_a_negation_of_uninterrupted():
    text = "Estar empadronado en el municipio de Getafe durante un periodo no inferior a 5 años ininterrumpidos."
    document = Document.desde_parrafos([[text]], seccion="requisitos")
    context = ExtractionContext("x", date(2026, 11, 27), Municipios.load(DATA_DIR))
    (result,) = EmpadronamientoExtractor().extract(document, context)
    assert result.valor["anios_min"] == 5
    assert result.valor["ininterrumpido"] is True

