"""Income and effort-rate rules on standalone Spanish sentences. The sentences are synthetic."""

from datetime import date

import pytest
from conftest import DATA_DIR

from vpo.core.normalize import Municipios
from vpo.extraction.base import Document, ExtractionContext
from vpo.extraction.rules.ingresos_iprem import IngresosIpremExtractor

CTX = ExtractionContext(fuente_id="demo", fecha_ref=date(2026, 11, 27), municipios=Municipios.load(DATA_DIR))
MIN = "/requisitos/ingresos_min_iprem"
MAX = "/requisitos/ingresos_max_iprem"
MIEMBROS = "/requisitos/ingresos_por_miembros"
PAGAS = "/requisitos/iprem_pagas"
EJERCICIO = "/requisitos/iprem_ejercicio"
ESFUERZO = "/requisitos/tasa_esfuerzo_max"


def extract(*parrafos: str, **kwargs):
    return IngresosIpremExtractor().extract(Document.desde_parrafos([list(parrafos)], **kwargs), CTX)


def found(*parrafos: str, campos=(MIN, MAX)) -> set:
    return {(r.campo, r.valor) for r in extract(*parrafos) if r.campo in campos}


@pytest.mark.parametrize(
    "frase, valor",
    [
        ("Los ingresos de la unidad familiar no excedan de 5,5 veces el IPREM.", 5.5),
        ("Ingresos que no superen 7,5 veces el IPREM.", 7.5),
        ("Los ingresos no podrán exceder de 5,5 veces el Indicador Público de Renta de Efectos Múltiples.", 5.5),
        ("No superiores a 5,5 veces el Indicador Público de Renta de Efectos Múltiples (IPREM).", 5.5),
        ("Tener unos ingresos inferiores a 5,5 veces el IPREM.", 5.5),
        ("Ingresos iguales o inferiores a 3,5 veces el IPREM.", 3.5),
        ("Ingresos anuales de hasta 7,5 veces el IPREM.", 7.5),
        ("Ingresos máximos: 5,5 veces el IPREM.", 5.5),
        ("El límite máximo de ingresos de la unidad de convivencia será de 5,5 veces el IPREM.", 5.5),
        ("Los ingresos serán, como máximo, 5,5 veces el IPREM.", 5.5),
        ("Ingresos de 5,5 veces el IPREM como máximo.", 5.5),
        ("Que no superen cinco coma cinco (5,5) veces el IPREM.", 5.5),
        ("Que no superen cinco veces y media el IPREM.", 5.5),
        ("Ingresos que no sean superiores a 5,5 veces el importe del IPREM.", 5.5),
        ("Ingresos no superiores a 7,5 IPREM.", 7.5),
        ("Sin que sus ingresos superen 5,5 veces el IPREM.", 5.5),
    ],
)
def test_maximum(frase, valor):
    results = extract(frase)
    assert [(r.campo, r.valor, r.regla) for r in results] == [(MAX, valor, "REG-IPREM-01")]


@pytest.mark.parametrize(
    "frase, valor",
    [
        ("Los ingresos no serán inferiores a 2,5 veces el IPREM.", 2.5),
        ("Ingresos mínimos de 1,5 veces el IPREM.", 1.5),
        ("Acreditar al menos 2 veces el IPREM.", 2.0),
        ("Tener ingresos superiores a 2,5 veces el IPREM.", 2.5),
        ("Ingresos iguales o superiores a 3,5 veces el IPREM.", 3.5),
        ("Ingresos mínimos superiores a 2,5 veces el Indicador Público de Renta a Efectos Múltiples.", 2.5),
        ("Los ingresos no podrán ser inferiores a una vez el IPREM.", 1.0),
    ],
)
def test_minimum(frase, valor):
    results = extract(frase)
    assert [(r.campo, r.valor, r.regla) for r in results] == [(MIN, valor, "REG-IPREM-02")]


@pytest.mark.parametrize(
    "frase",
    [
        "Ingresos comprendidos entre 1,5 y 7,5 veces el IPREM.",
        "Ingresos entre 1,5 veces y 7,5 veces el Indicador Público de Renta de Efectos Múltiples (IPREM).",
        "Ingresos desde 1,5 hasta 7,5 veces el IPREM.",
        "Ingresos de 1,5 a 7,5 veces el IPREM.",
    ],
)
def test_range(frase):
    results = extract(frase)
    assert {(r.campo, r.valor, r.regla) for r in results} == {
        (MIN, 1.5, "REG-IPREM-03"),
        (MAX, 7.5, "REG-IPREM-03"),
    }


@pytest.mark.parametrize(
    "frase",
    [
        "Ingresos no inferiores a 2,5 veces el IPREM ni superiores a 5,5 veces el IPREM.",
        "Ingresos no inferiores a 2,5 veces ni superiores a 5,5 veces el IPREM.",
        "Ingresos no inferiores a 2,5 ni superiores a 5,5 veces el IPREM.",
        "Ingresos mínimos de 2,5 veces el IPREM y máximos de 5,5 veces el IPREM.",
        "Ingresos superiores a 2,5 veces el IPREM e inferiores a 5,5 veces el IPREM.",
    ],
)
def test_two_limits(frase):
    assert found(frase) == {(MIN, 2.5), (MAX, 5.5)}


def test_two_different_maxima_are_both_emitted():
    assert found("Ingresos no superiores a 5,5 veces el IPREM en VPPB y a 7,5 veces el IPREM en VPPL.") == {
        (MAX, 5.5),
        (MAX, 7.5),
    }


@pytest.mark.parametrize(
    "frase, esperado",
    [
        (
            "Mínimos de 1,5 veces el Indicador Público de Renta de Efectos Múltiples, y máximos de 3,5 veces del "
            "mismo indicador.",
            {(MIN, 1.5), (MAX, 3.5)},
        ),
        (
            "Ingresos máximos: 5,5 veces el IPREM, si se trata de viviendas de precio básico (VPPB) y 7,5 veces "
            "IPREM si se tratara de viviendas de precio limitado (VPPL).",
            {(MAX, 5.5), (MAX, 7.5)},
        ),
        ("Los ingresos no pueden superar el resultado de multiplicar por 5,5 el último IPREM.", {(MAX, 5.5)}),
    ],
)
def test_wordings_of_real_calls(frase, esperado):
    assert found(frase) == esperado


def test_special_group_limit_is_not_the_general_one():
    frase = "Los ingresos no podrán exceder de 5,5 veces el IPREM, o de 7 veces el IPREM para familias numerosas."
    assert found(frase) == {(MAX, 5.5)}


@pytest.mark.parametrize(
    "frase",
    [
        "El IPREM se multiplica por 5,5 veces el IPREM según la tabla.",
        "Se tendrá en cuenta la cifra de 5,5 veces el IPREM.",
        "Quedarán excluidos quienes tengan ingresos superiores a 5,5 veces el IPREM.",
        "Serán excluidas las solicitudes cuyos ingresos no superen 2,5 veces el IPREM.",
        "Quienes superen 5,5 veces el IPREM deberán justificarlo.",
        "Se reservará un 10% de viviendas para ingresos inferiores a 2,5 veces el IPREM.",
        "Tendrán preferencia las unidades con ingresos no superiores a 3,5 veces el IPREM.",
        "Ingresos inferiores a 2,5 veces el IPREM: 10 puntos.",
        "Se exigirá aval cuando los ingresos sean inferiores a 3 veces el IPREM.",
        "Para unidades de 1 o 2 miembros, ingresos no superiores a 4,5 veces el IPREM.",
        "En viviendas de 3 dormitorios los ingresos mínimos serán de 3 veces el IPREM.",
        "Los ingresos mínimos deberán ser 3 veces la renta anual y se calculará el IPREM.",
        "No ser titular de vivienda y que los ingresos sean superiores a 2,5 veces el IPREM.",
        "Ingresos no superiores a 5,5 veces el salario mínimo interprofesional.",
    ],
)
def test_no_limit(frase):
    assert found(frase) == set()


def test_priority_heading_discards_its_list():
    assert found("Baremo de puntuación:", "a) Ingresos no superiores a 2,5 veces el IPREM.") == set()


def test_confidence_and_evidence():
    frase = "Ingresos no superiores a 5,5 veces el IPREM."
    assert extract(frase)[0].confianza == 0.85
    assert extract(frase, seccion="requisitos")[0].confianza == 0.95
    assert extract(frase, normativo=True)[0].confianza == 0.55
    assert extract(frase)[0].evidencia == frase


@pytest.mark.parametrize(
    "frase, pagas",
    [
        ("El IPREM se computará en 14 pagas.", 14),
        ("IPREM anual (14 pagas).", 14),
        ("Indicador Público de Renta de Efectos Múltiples (IPREM), en catorce pagas.", 14),
        ("Se toma el IPREM de 12 pagas.", 12),
        ("Calculado en 14 pagas del IPREM.", 14),
    ],
)
def test_payments(frase, pagas):
    assert [(r.valor, r.regla) for r in extract(frase)] == [(pagas, "REG-IPREM-05")]


@pytest.mark.parametrize(
    "frase",
    [
        "La nómina se abona en 14 pagas.",
        "Multiplique el salario mensual por 14 pagas para compararlo con el IPREM.",
        "El IPREM no incluye las 12 pagas extraordinarias.",
        "La fianza se fracciona en 12 mensualidades.",
    ],
)
def test_no_payments(frase):
    assert found(frase, campos=(PAGAS,)) == set()


@pytest.mark.parametrize(
    "frase",
    [
        "Ingresos según la declaración de la renta del ejercicio 2025.",
        "Se computarán los ingresos del ejercicio 2025.",
        "Ingresos acreditados con el IRPF 2025.",
        "Se aplicará el IPREM del año 2025.",
    ],
)
def test_year(frase):
    assert [(r.valor, r.regla) for r in extract(frase)] == [(2025, "REG-IPREM-06")]


@pytest.mark.parametrize(
    "frase",
    [
        "El presupuesto del ejercicio 2025 fue aprobado.",
        "IPREM fijado en la Ley de Presupuestos para el ejercicio 2023.",
        "Ingresos del ejercicio 2024 o 2025.",
        "La obra finaliza en 2025.",
        "Copia de la declaración de la renta del ejercicio 2024.",
    ],
)
def test_no_year(frase):
    assert found(frase, campos=(EJERCICIO,)) == set()


@pytest.mark.parametrize(
    "frase, regla",
    [
        ("La renta anual no podrá superar el 35 % de los ingresos de la unidad familiar.", "REG-ESF-01"),
        ("El alquiler no superará el treinta y cinco por ciento (35%) de los ingresos.", "REG-ESF-01"),
        ("El importe de la renta no podrá ser superior al 35 por 100 de los ingresos.", "REG-ESF-01"),
        ("No destinen más del 35% de sus ingresos al pago del alquiler.", "REG-ESF-01"),
        ("La tasa de esfuerzo máxima será del 35%.", "REG-ESF-02"),
    ],
)
def test_effort_rate(frase, regla):
    assert [(r.campo, r.valor, r.regla) for r in extract(frase)] == [(ESFUERZO, 0.35, regla)]


@pytest.mark.parametrize(
    "frase",
    [
        "La renta incluye una bonificación que no podrá superar el 35% de los ingresos.",
        "La renta se incrementará con el IVA del 10%.",
        "La actualización de la renta no podrá superar el 2% del índice de referencia.",
        "Se reservará un 35% de las viviendas en alquiler.",
        "La renta tiene un descuento del 35% sobre el precio máximo.",
        "Los demás gastos no podrán superar el 35% de los ingresos.",
        "La tasa de esfuerzo mínima será del 20%.",
    ],
)
def test_no_effort_rate(frase):
    assert found(frase, campos=(ESFUERZO,)) == set()


def table(*rows: tuple[str, ...], texts=("Ingresos por tamaño de la unidad.",)):
    doc = Document.desde_parrafos([list(texts)], tablas={1: [tuple(rows)]})
    return IngresosIpremExtractor().extract(doc, CTX)


def row(desde, hasta, minimo, maximo) -> dict:
    return {"miembros_desde": desde, "miembros_hasta": hasta, "min_iprem": minimo, "max_iprem": maximo}


def test_stepped_table():
    results = table(
        ("Nº de miembros", "Mínimo (veces IPREM)", "Máximo (veces IPREM)"),
        ("1 o 2", "2", "4,5"),
        ("3", "2,5", "5,5"),
        ("4 o más", "3", "6,5"),
    )
    assert [(r.campo, r.regla, r.metodo, r.pagina) for r in results] == [(MIEMBROS, "REG-IPREM-04", "pdf_tabla", 1)]
    assert results[0].valor == [row(1, 2, 2.0, 4.5), row(3, 3, 2.5, 5.5), row(4, None, 3.0, 6.5)]


def test_stepped_table_with_two_header_rows_and_euro_columns():
    results = table(
        ("Miembros de la unidad familiar", "Ingresos IPREM", "", "Ingresos en euros"),
        ("", "Mínimo", "Máximo", "Máximo"),
        ("1", "2 veces", "5,5 veces", "46.200 €"),
        ("Más de 1", "2,5 veces", "6 veces", "50.400 €"),
    )
    assert results[0].valor == [row(1, 1, 2.0, 5.5), row(2, None, 2.5, 6.0)]


def test_stepped_table_with_a_single_column():
    results = table(("Miembros", "IPREM"), ("Hasta 2", "Hasta 5,5"), ("3 o más", "Hasta 6,5"))
    assert results[0].valor == [row(1, 2, None, 5.5), row(3, None, None, 6.5)]


@pytest.mark.parametrize(
    "rows",
    [
        (("Miembros", "Puntos IPREM máximo"), ("1", "5"), ("2", "4")),
        (("Miembros", "Máximo en euros"), ("1", "46.200"), ("2", "50.400")),
        (("Miembros", "IPREM"), ("1", "4,5"), ("2", "5,5")),  # minimum or maximum?
        (("Miembros", "IPREM máximo VPPB", "IPREM máximo VPPL"), ("1", "5,5", "7,5")),
        (("Miembros", "IPREM máximo"), ("1", "4,5"), ("resto", "5,5")),
        (("Dormitorios", "IPREM máximo"), ("1", "4,5"), ("2", "5,5")),
    ],
)
def test_tables_that_are_not_read(rows):
    assert table(*rows) == []


def test_flat_figures_of_the_table_are_not_repeated():
    results = table(
        ("Miembros", "IPREM máximo"),
        ("1", "4,5"),
        ("2 o más", "5,5"),
        texts=("Los ingresos no superarán 5,5 veces el IPREM ni serán inferiores a 2 veces el IPREM.",),
    )
    assert {(r.campo, r.valor if r.campo != MIEMBROS else None) for r in results} == {(MIEMBROS, None), (MIN, 2.0)}
