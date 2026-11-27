from datetime import date

import pytest
from conftest import DATA_DIR

from vpo.core.models import Tipologia
from vpo.core.normalize import Municipios
from vpo.extraction.base import Document, ExtractionContext, FieldResult
from vpo.extraction.rules import tipologias as t
from vpo.extraction.rules.rentas import RentasExtractor

CTX = ExtractionContext("demo", date(2026, 11, 27), Municipios.load(DATA_DIR))
CAB = ("Nº dormitorios", "Superficie útil (m²)", "Renta mensual (€)")


def run(*parrafos: str, tablas=None, paginas=None, **kwargs) -> list[FieldResult]:
    doc = Document.desde_parrafos(paginas or [list(parrafos)], tablas=tablas, **kwargs)
    return RentasExtractor().extract(doc, CTX)


def tipologias(*parrafos: str, **kwargs) -> list[list[dict]]:
    return [r.valor for r in run(*parrafos, **kwargs) if r.campo == "/tipologias"]


def de_tabla(*tabla) -> list[list[dict]]:
    return tipologias("Texto.", tablas={1: [tuple(tabla)]})


def notas(*parrafos: str) -> list[str]:
    return [r.valor for r in run(*parrafos) if r.campo == "/requisitos/otros"]


def resumen(rows: list[dict]) -> list[tuple]:
    keys = ("dormitorios", "superficie_util_m2", "renta_mensual_eur", "renta_mensual_max_eur", "num_viviendas")
    return [tuple(row[k] for k in keys) for row in rows]


# -- REG-RENTA-01 -------------------------------------------------------------------------------


def test_simple_table():
    results = run("Texto.", tablas={1: [(CAB, ("2", "60,50", "1.034,56 €"), ("1", "45", "500,00"))]})
    (result,) = results
    assert resumen(result.valor) == [(1, 45.0, 500.0, None, None), (2, 60.5, 1034.56, None, None)]
    assert (result.regla, result.metodo, result.pagina) == ("REG-RENTA-01", "pdf_tabla", 1)
    assert result.confianza == 0.9
    for row in result.valor:
        Tipologia.model_validate(row)


def test_multi_row_header_with_merged_cells_and_annex_columns():
    (rows,) = de_tabla(
        ("Tipología", "Superficie", "", "Nº de\nviviendas", "Renta mensual", "", ""),
        ("", "Útil", "Construida", "", "Vivienda", "Garaje", "Trastero"),
        ("1 dormitorio", "42,10", "55,00", "12", "450,00 €", "50,00 €", "15,00 €"),
        ("2 dormitorios adaptada", "58,00", "75,00", "3", "610,00 €", "50,00 €", "-"),
    )
    assert resumen(rows) == [(1, 42.1, 450.0, None, 12), (2, 58.0, 610.0, None, 3)]
    assert rows[0]["garaje"] == {"disponibilidad": "desconocido", "precio_mensual_eur": 50.0}
    assert rows[0]["trastero"] == {"disponibilidad": "desconocido", "precio_mensual_eur": 15.0}
    assert rows[1]["adaptada_pmr"] is True
    assert rows[1]["trastero"] == {"disponibilidad": "desconocido", "precio_mensual_eur": None}


def test_title_row_range_cells_total_row_and_vertically_merged_bedrooms():
    (rows,) = de_tabla(
        ("PROMOCIÓN DEMO", "", ""),
        ("Dormito-\nrios", "Superficie útil", "Renta"),
        ("2", "60", "500 - 550 €"),
        ("", "70", "600 €"),
        ("TOTAL", "", "1.150"),
    )
    assert resumen(rows) == [(2, 60.0, 500.0, 550.0, None), (2, 70.0, 600.0, None, None)]


def test_minimum_and_maximum_columns():
    (rows,) = de_tabla(("Dormitorios", "Renta mínima mensual", "Renta máxima mensual"), ("3", "700", "900"))
    assert resumen(rows) == [(3, None, 700.0, 900.0, None)]


def test_individual_dwellings_are_aggregated():
    (rows,) = de_tabla(
        ("Portal", "Planta", "Dormitorios", "Sup. útil", "Alquiler mensual"),
        ("1", "1º", "1", "40,0", "400,00"),
        ("1", "2º", "1", "41,0", "420,00"),
        ("1", "3º", "2", "60,0", "600,00"),
        ("2", "1º", "2", "60,0", "600,00"),
    )
    assert resumen(rows) == [(1, None, 400.0, 420.0, 2), (2, 60.0, 600.0, None, 2)]


def test_headerless_continuation_on_the_next_page():
    first = (("Vivienda", "Dormitorios", "Renta mensual"), ("1A", "1", "400"))
    second = (("1B", "1", "410"),)
    results = run(paginas=[["a"], ["b"]], tablas={1: [first], 2: [second]})
    (result,) = results
    assert resumen(result.valor) == [(1, None, 400.0, 410.0, 2)]
    assert result.confianza == 0.85


def test_two_different_tables_give_two_candidates():
    one = (CAB, ("1", "45", "500"))
    two = (CAB, ("1", "45", "650"))
    assert len(tipologias("x", tablas={1: [one, two]})) == 2


def test_tables_that_count_their_dwellings_add_up():
    head = ("Dormitorios", "Número de viviendas", "Renta mensual")
    (rows,) = (r.valor for r in run(paginas=[["x"]], tablas={1: [(head, ("1", "10", "500")), (head, ("1", "4", "650"))]}))
    assert resumen(rows) == [(1, None, 500.0, None, 10), (1, None, 650.0, None, 4)]


def test_annex_presence_column():
    (rows,) = de_tabla(("Dormitorios", "Renta mensual", "Plaza de garaje"), ("1", "500", "Incluida"))
    assert rows[0]["garaje"] == {"disponibilidad": "incluido", "precio_mensual_eur": None}
    (rows,) = de_tabla(("Dormitorios", "Renta mensual", "Garaje"), ("1", "500", "1"))
    assert rows[0]["garaje"] == {"disponibilidad": "desconocido", "precio_mensual_eur": None}


@pytest.mark.parametrize(
    "tabla",
    [
        # income limits
        (("Miembros unidad familiar", "Ingresos máximos anuales"), ("1", "25.000"), ("2", "30.000")),
        (("Nº dormitorios", "Ingresos mínimos mensuales"), ("1", "1.200")),
        (("INGRESOS MÁXIMOS", ""), ("Dormitorios", "Renta"), ("1", "2.000")),
        # deposits
        (("Dormitorios", "Fianza"), ("1", "900")),
        (("Dormitorios", "Importe de la garantía mensual"), ("1", "900")),
        # annual rents, sale prices, rents per m2
        (("Dormitorios", "Renta anual"), ("1", "6.000")),
        (("Dormitorios", "Precio máximo de venta"), ("1", "1.900")),
        (("Dormitorios", "Precio"), ("1", "1.900")),
        (("Dormitorios", "Renta (€/m² útil/mes)"), ("1", "7")),
        # garage prices are not dwelling rents
        (("Tipología", "Renta plaza de garaje"), ("1 dormitorio", "200")),
        (("Tipo", "Precio alquiler"), ("Garaje", "200"), ("Trastero", "150")),
        # no bedrooms to speak of
        (("Tipo", "Renta mensual"), ("A", "500")),
        # with or without VAT: which one is the rent?
        (("Dormitorios", "Renta mensual", "Renta mensual con IVA"), ("1", "500", "550")),
        # a row with a rent that cannot be understood invalidates the table
        (("Dormitorios", "Renta mensual"), ("1", "500"), ("2 y 3", "700")),
        # nothing but empty rents
        (("Dormitorios", "Renta mensual"), ("1", "según ingresos")),
    ],
)
def test_tables_that_are_not_rent_tables(tabla):
    assert de_tabla(*tabla) == []


def test_unreadable_values_stay_null():
    (rows,) = de_tabla(CAB, ("1", "45-50", "500"), ("2", "60", "consultar"))
    assert resumen(rows) == [(1, None, 500.0, None, None), (2, 60.0, None, None, None)]


def test_cell_readers():
    assert t.leer_importe("desde 600 a 700 €/mes") == (600.0, 700.0)
    assert t.leer_importe("600.00") is None
    assert t.leer_importe("hasta 600") is None
    assert t.leer_dormitorios("2", columna_dormitorios=False) is None
    assert t.leer_dormitorios("estudio", columna_dormitorios=False) == 0
    assert t.leer_dormitorios("1 o 2 dormitorios", columna_dormitorios=True) is None


# -- REG-RENTA-02 / 03 --------------------------------------------------------------------------


def test_rent_in_running_text():
    results = run(
        "Las rentas serán: viviendas de 1 dormitorio, 450 euros al mes; de 2 dormitorios, 575,50 €/mes.",
        seccion="rentas",
    )
    (result,) = results
    assert resumen(result.valor) == [(1, None, 450.0, None, None), (2, None, 575.5, None, None)]
    assert (result.regla, result.metodo, result.confianza) == ("REG-RENTA-02", "pdf_texto", 0.9)


def test_one_candidate_aggregates_the_whole_document():
    (rows,) = tipologias("1 dormitorio: 450 euros mensuales.", "2D de 60 m2 útiles: 575 euros mensuales.")
    assert resumen(rows) == [(1, None, 450.0, None, None), (2, 60.0, 575.0, None, None)]


def test_contradicting_rents_give_two_candidates():
    found = tipologias("1 dormitorio: 450 euros al mes.", "La renta de 1 dormitorio es de 480 euros al mes.")
    assert [resumen(rows) for rows in found] == [[(1, None, 450.0, None, None)], [(1, None, 480.0, None, None)]]


def test_range():
    results = run("La renta mensual oscila desde 400 euros hasta 650 euros.")
    assert results[0].regla == "REG-RENTA-03"
    assert resumen(results[0].valor) == [(None, None, 400.0, 650.0, None)]
    (rows,) = tipologias("Alquiler de viviendas de 2 dormitorios desde 500 € hasta 600 € al mes.")
    assert resumen(rows) == [(2, None, 500.0, 600.0, None)]


def test_legal_quotes_have_low_confidence():
    results = run("1 dormitorio: 450 euros al mes.", normativo=True)
    assert results[0].confianza == 0.5


@pytest.mark.parametrize(
    "frase",
    [
        "Para viviendas de 2 dormitorios la fianza es de 900 euros.",
        "Viviendas de 2 dormitorios: ingresos mínimos de 1.500 euros mensuales.",
        "Viviendas de 2 dormitorios: renta anual de 2.400 euros.",
        "Viviendas de 2 dormitorios con renta de 2.400 euros anuales.",
        "El precio de venta de la vivienda de 2 dormitorios es de 1.900 euros al mes.",
        "Viviendas de 2 dormitorios. La renta se actualizará cada año en 200 euros.",
        "Viviendas de 2 dormitorios, plaza de garaje por 200 euros al mes.",
        "Viviendas de 1, 2 y 3 dormitorios con renta desde 500 euros al mes.",
        "Por 500 euros 1 dormitorio y por 600 euros 2 dormitorios, renta mensual.",
        "La renta de 2 dormitorios es de 7,50 euros/m2 al mes.",
        "El alquiler de 1 dormitorio es de 100 euros al mes.",
        "Unidades de 2 dormitorios: 600 euros.",
        "Los ingresos estarán entre 1.000 y 2.000 euros mensuales.",
        "La fianza va desde 400 euros hasta 650 euros según la renta.",
    ],
)
def test_amounts_that_are_not_rents(frase):
    assert tipologias(frase) == []


# -- REG-RENTA-04 and notes ---------------------------------------------------------------------


def test_rent_per_m2_is_never_turned_into_a_rent():
    assert tipologias("La renta máxima será de 7,50 euros/m2 útil al mes.") == []


def test_rent_per_m2_is_quoted_next_to_a_surface():
    (result,) = run("La renta es de 7,50 €/m2 útil.", tablas={1: [(CAB, ("1", "45", "500"))]})
    assert "REG-RENTA-04: 7,50 €/m2 útil" in result.evidencia
    assert result.valor[0]["renta_mensual_eur"] == 500.0


def test_vat_and_community_fee_notes():
    assert notas("La renta es de 500 euros, IVA no incluido.") == ["IVA no incluido"]
    assert notas("Plaza de garaje: 50 euros más IVA.") == ["IVA no incluido"]
    assert notas("En la renta están incluidos los gastos de comunidad.") == ["Gastos de comunidad incluidos"]
    assert notas("Renta con gastos de comunidad no incluidos.") == ["Gastos de comunidad no incluidos"]


def test_no_notes_out_of_context_or_when_contradictory():
    assert notas("El precio de venta de la plaza de garaje es de 9.000 euros más IVA.") == []
    assert notas("El presupuesto de la obra es de 3 millones, IVA incluido.") == []
    assert notas("Renta de la vivienda, IVA incluido.", "Alquiler del garaje, IVA no incluido.") == []
