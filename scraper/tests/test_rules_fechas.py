from datetime import date

import pytest
from conftest import DATA_DIR

from vpo.core.normalize import Municipios
from vpo.extraction.base import Document, ExtractionContext, FieldResult
from vpo.extraction.rules.fechas import ENTREGA, FIN, INICIO, SORTEO, FechasExtractor

CTX = ExtractionContext("demo", date(2026, 11, 27), Municipios.load(DATA_DIR))


def run(*parrafos: str, **kwargs) -> list[FieldResult]:
    return FechasExtractor().extract(Document.desde_parrafos([list(parrafos)], **kwargs), CTX)


def valores(*parrafos: str) -> list[tuple[str, str]]:
    return [(r.campo, r.valor) for r in run(*parrafos)]


def rango(inicio: str, fin: str) -> list[tuple[str, str]]:
    return [(INICIO, inicio), (FIN, fin)]


@pytest.mark.parametrize(
    ("parrafos", "esperado"),
    [
        (
            ["El plazo de presentación de solicitudes será del 1 de marzo de 2026 al 31 de marzo de 2026."],
            rango("2026-03-01", "2026-03-31"),
        ),
        (["Inscripción desde el 02/03/2026 hasta el 15/04/2026."], rango("2026-03-02", "2026-04-15")),
        (["Plazo de solicitudes: del 1 al 15 de marzo de 2026."], rango("2026-03-01", "2026-03-15")),
        (["Plazo: del 20 de diciembre al 10 de enero de 2027."], rango("2026-12-20", "2027-01-10")),
        (["PLAZO DE PRESENTACIÓN", "Del 1 de marzo al 15 de abril de 2026."], rango("2026-03-01", "2026-04-15")),
        (
            [
                "Las solicitudes se presentarán desde las 9:00 horas del día 2 de marzo de 2026 "
                "hasta las 14:00 horas del día 20 de marzo de 2026."
            ],
            rango("2026-03-02", "2026-03-20"),
        ),
    ],
)
def test_registration_range(parrafos, esperado):
    assert valores(*parrafos) == esperado


def test_result_metadata():
    results = run("Plazo de solicitudes: del 1 al 15 de marzo de 2026.", seccion="plazos")
    assert {(r.regla, r.metodo, r.pagina, r.confianza) for r in results} == {("REG-FECHA-03", "pdf_texto", 1, 0.95)}


def test_two_ranges_are_both_emitted():
    found = valores("Plazo de solicitudes: del 1 al 15 de marzo de 2026.", "Plazo: del 1 al 15 de abril de 2026.")
    assert found == rango("2026-03-01", "2026-03-15") + rango("2026-04-01", "2026-04-15")


@pytest.mark.parametrize(
    "frase",
    [
        "El sorteo se celebrará el día 12 de marzo de 2026.",
        "Fecha del sorteo: 12/03/2026.",
        "El sorteo ante notario tendrá lugar el próximo jueves, 12 de marzo de 2026.",
        "El 12 de marzo de 2026 se celebrará el sorteo.",
        "Resultarán incluidos en el sorteo del 12 de marzo de 2026.",
    ],
)
def test_lottery(frase):
    assert valores(frase) == [(SORTEO, "2026-03-12")]


@pytest.mark.parametrize(
    ("frase", "esperado"),
    [
        ("Entrega de llaves prevista en el segundo trimestre de 2027.", "2027-T2"),
        ("Entrega prevista: 3T 2027.", "2027-T3"),
        ("La fecha prevista de entrega es marzo de 2027.", "2027-03"),
        ("Finalización de las obras: 15/09/2027.", "2027-09"),
        ("Las viviendas se entregarán a lo largo de 2028.", "2028"),
    ],
)
def test_expected_handover(frase, esperado):
    assert valores(frase) == [(ENTREGA, esperado)]


@pytest.mark.parametrize(
    "frase",
    [
        # dates of laws and gazettes
        "Conforme al Decreto 74/2009, de 30 de julio de 2009, que regula las solicitudes.",
        "El sorteo se regirá por la Orden de 5 de mayo de 2020.",
        "El sorteo se realizará según el Decreto 74/2009, de 30 de julio de 2009.",
        # unclassified dates and other terms
        "Firmado en Madrid el 3 de marzo de 2026.",
        "Los ingresos obtenidos del 1 de enero de 2025 al 31 de diciembre de 2025 constarán en la solicitud.",
        "Plazo de subsanación de solicitudes: del 1 al 15 de marzo de 2026.",
        "Plazo de alegaciones: del 1 al 15 de marzo de 2026.",
        "Las visitas serán del 1 al 15 de marzo de 2026.",
        # relative terms
        "El plazo de solicitudes será de 20 días naturales desde el 1 de marzo de 2026.",
        "El sorteo se celebrará en el plazo de veinte días desde el 1 de marzo de 2026.",
        "La entrega de llaves se hará en el plazo de 3 meses desde la licencia de 2026.",
        # near misses
        "El listado del sorteo se publicará el 12 de marzo de 2026.",
        "Participarán en el sorteo los empadronados antes del 1 de enero de 2026.",
        "Entrega de la solicitud en 2026.",
        "Las obras finalizaron en 2019.",
        # impossible or reversed
        "Fecha del sorteo: 31/02/2026.",
        "Plazo de solicitudes: del 15/04/2026 al 01/03/2026.",
    ],
)
def test_no_date_without_a_clear_context(frase):
    assert valores(frase) == []
