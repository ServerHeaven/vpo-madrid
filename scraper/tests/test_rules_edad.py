"""Age rules on standalone Spanish sentences. The sentences are synthetic."""

from datetime import date

import pytest
from conftest import DATA_DIR

from vpo.core.normalize import Municipios
from vpo.extraction.base import Document, ExtractionContext
from vpo.extraction.rules.edad import EdadExtractor

CTX = ExtractionContext(fuente_id="demo", fecha_ref=date(2026, 11, 27), municipios=Municipios.load(DATA_DIR))
CAMPO = "/requisitos/edad"


def extract(*parrafos: str, **kwargs):
    return EdadExtractor().extract(Document.desde_parrafos([list(parrafos)], **kwargs), CTX)


def edad(minimo=None, maximo=None, tipo="requisito") -> dict:
    return {"min": minimo, "max": maximo, "tipo": tipo}


@pytest.mark.parametrize(
    "frase, valor, regla",
    [
        ("Los solicitantes deberán ser menores de 35 años.", edad(maximo=34), "REG-EDAD-01"),
        ("Ser menor de treinta y cinco (35) años.", edad(maximo=34), "REG-EDAD-01"),
        ("No haber cumplido los 36 años.", edad(maximo=35), "REG-EDAD-01"),
        ("No haber cumplido 36 años al final del plazo de solicitudes.", edad(maximo=35), "REG-EDAD-01"),
        ("Tener una edad máxima de 35 años.", edad(maximo=35), "REG-EDAD-01"),
        ("No haber alcanzado la edad de 35 años.", edad(maximo=34), "REG-EDAD-01"),
        ("Tener una edad de hasta 40 años.", edad(maximo=40), "REG-EDAD-01"),
        ("Tener una edad no superior a 35 años.", edad(maximo=35), "REG-EDAD-01"),
        ("El solicitante no podrá ser mayor de 50 años.", edad(maximo=50), "REG-EDAD-01"),
        ("Tener entre 18 y 50 años.", edad(18, 50), "REG-EDAD-02"),
        ("Edad comprendida entre los 18 y los 35 años, ambos inclusive.", edad(18, 35), "REG-EDAD-02"),
        ("Tener de 18 a 35 años de edad.", edad(18, 35), "REG-EDAD-02"),
        ("Haber cumplido 18 años y no haber cumplido 36 años.", edad(18, 35), "REG-EDAD-02"),
        ("Ser mayor de 18 años y menor de 35 años.", edad(18, 34), "REG-EDAD-02"),
        ("Ser mayores de 18 y menores de 35 años.", edad(18, 34), "REG-EDAD-02"),
        ("Los solicitantes deberán ser mayores de 18 años.", edad(18), "REG-EDAD-03"),
        ("Tener una edad mínima de 18 años.", edad(18), "REG-EDAD-03"),
        ("El titular no podrá ser menor de 18 años.", edad(18), "REG-EDAD-03"),
    ],
)
def test_requirement(frase, valor, regla):
    results = extract(frase)
    assert [(r.campo, r.valor, r.regla) for r in results] == [(CAMPO, valor, regla)]
    assert results[0].evidencia == frase


@pytest.mark.parametrize(
    "frase, valor",
    [
        ("Cupo para jóvenes menores de 35 años.", edad(maximo=34, tipo="cupo")),
        ("Se reservará un 10% de las viviendas a mayores de 65 años.", edad(65, tipo="cupo")),
    ],
)
def test_quota(frase, valor):
    assert [r.valor for r in extract(frase)] == [valor]


def test_quota_announced_by_the_heading():
    results = extract("Cupo de jóvenes:", "a) Ser menor de 35 años.")
    assert [r.valor for r in results] == [edad(maximo=34, tipo="cupo")]


def test_requirement_and_quota_are_both_emitted():
    results = extract(
        "Tener entre 18 y 65 años.",
        "Cupo para jóvenes menores de 35 años.",
    )
    assert [r.valor for r in results] == [edad(18, 65), edad(maximo=34, tipo="cupo")]


@pytest.mark.parametrize(
    "frase",
    [
        "Familias con hijos menores de 25 años a cargo.",
        "Unidades con descendientes menores de 26 años.",
        "Los miembros mayores de 16 años deberán aportar la declaración.",
        "Deberán firmar la solicitud todos los mayores de 18 años.",
        "Cupo de movilidad reducida: personas mayores de 65 años.",
        "Los menores de 14 años no necesitan DNI.",
        "Tendrán preferencia los menores de 35 años.",
        "Por ser menor de 35 años: 2 puntos.",
        "El contrato tendrá una duración de entre 25 y 50 años.",
        "El edificio deberá ser de antigüedad menor de 30 años.",
        "Ser mayor de 18 años o menor emancipado.",
        "Ser mayor de edad.",
        "Tener 35 años o menos.",
        "Ser menor de 35 años o de 35 años inclusive.",
        "Estar empadronado durante al menos 3 años.",
    ],
)
def test_not_an_age_limit(frase):
    assert extract(frase) == []


@pytest.mark.parametrize(
    "frase",
    [
        "Se podrá solicitar sin límite de edad.",
        "No existe límite de edad para participar.",
        "No se establece ningún requisito de edad.",
    ],
)
def test_explicitly_no_limit(frase):
    assert [(r.campo, r.valor, r.regla) for r in extract(frase)] == [
        ("/requisitos/no_exigidos", "edad", "REG-EDAD-04")
    ]


@pytest.mark.parametrize(
    "frase",
    [
        "Hijos con discapacidad sin límite de edad.",
        "Los descendientes computan sin límite de edad si conviven.",
        "No hay límite de edad salvo en el cupo joven.",
        "No se exige edad máxima.",
    ],
)
def test_qualified_absence_is_not_emitted(frase):
    assert [r for r in extract(frase) if r.campo == "/requisitos/no_exigidos"] == []


def test_confidence():
    frase = "Los solicitantes deberán ser menores de 35 años."
    assert extract(frase)[0].confianza == 0.85
    assert extract(frase, seccion="requisitos")[0].confianza == 0.95
    assert extract(frase, normativo=True)[0].confianza == 0.55
