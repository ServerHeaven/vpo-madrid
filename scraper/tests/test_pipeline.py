"""Resolution of candidates. Extractors are fakes returning hand-made results."""

import random
import sys
import types
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from vpo.core.normalize import Municipios
from vpo.extraction import pipeline
from vpo.extraction.base import CAMPO_GARAJE, Document, ExtractionContext, FieldResult, Page

CTX = ExtractionContext("demo", date(2026, 11, 27), Municipios.load(Path(__file__).resolve().parents[2] / "data"))
URL = "https://example.org/bases.pdf"
MAX = "/requisitos/ingresos_max_iprem"
MIN = "/requisitos/ingresos_min_iprem"
EMP = "/requisitos/empadronamiento"
NO = "/requisitos/no_exigidos"
EMPADRONAMIENTO = {
    "ambito": "municipio",
    "municipio_ine": "28079",
    "anios_min": 3,
    "ininterrumpido": None,
    "alternativa_trabajo": None,
}


def res(campo, valor, confianza=0.9, *, metodo="pdf_texto", documento=URL, regla="REG-TEST", pagina=1):
    return FieldResult(campo, valor, confianza, pagina, f"evidencia de {valor}", regla, metodo, documento)


def tipologia(dormitorios, renta):
    anejo = {"disponibilidad": "desconocido", "precio_mensual_eur": None}
    return {
        "dormitorios": dormitorios,
        "superficie_util_m2": None,
        "renta_mensual_eur": renta,
        "renta_mensual_max_eur": None,
        "num_viviendas": None,
        "garaje": dict(anejo),
        "trastero": dict(anejo),
        "adaptada_pmr": None,
    }


class Fake:
    version = "0.0.0"
    campos_soportados = frozenset()

    def __init__(self, *results, nombre="fake", error=None):
        self.results, self.nombre, self.error = list(results), nombre, error

    def extract(self, doc, ctx):
        if self.error:
            raise self.error
        return self.results


def resolve(*candidatos, **kwargs):
    return pipeline.resolver(candidatos, CTX, **kwargs)


def descarte(resultado, campo):
    return next(d for d in resultado.descartes if d.campo == campo)


def test_single_value_over_threshold_is_accepted():
    result = resolve(res(MAX, 5.5, 0.8))
    assert result.valor(MAX) == 5.5
    assert result.descartes == ()


def test_value_below_threshold_stays_null_but_is_listed():
    result = resolve(res(MAX, 5.5, 0.79))
    assert result.campos == ()
    assert descarte(result, MAX).motivo == "no_encontrado"
    assert [c.valor for c in descarte(result, MAX).candidatos] == [5.5]


def test_thresholds_are_configurable_per_field(monkeypatch):
    assert resolve(res(MAX, 5.5, 0.75), umbrales={MAX: 0.7}).valor(MAX) == 5.5
    monkeypatch.setitem(pipeline.UMBRALES, MAX, 0.95)
    assert resolve(res(MAX, 5.5, 0.9)).valor(MAX) is None


def test_equal_values_are_grouped_keeping_the_best_candidate():
    result = resolve(res(MAX, 5.5, 0.6), res(MAX, 5.50, 0.95, regla="REG-B"), res(MAX, 5.5, 0.85))
    assert [(c.confianza, c.regla) for c in result.campos] == [(0.95, "REG-B")]


def test_contradicting_values_give_null_and_a_conflict_with_both_candidates():
    result = resolve(res(MAX, 5.5, 0.95), res(MAX, 7.5, 0.55, pagina=4))
    assert result.valor(MAX) is None
    conflict = descarte(result, MAX)
    assert conflict.motivo == "conflicto"
    assert [(c.valor, c.pagina) for c in conflict.candidatos] == [(5.5, 1), (7.5, 4)]


def test_weak_rival_does_not_conflict():
    assert resolve(res(MAX, 5.5, 0.9), res(MAX, 7.5, 0.49)).valor(MAX) == 5.5


def test_candidates_from_several_documents_conflict():
    result = resolve(res(MAX, 5.5), res(MAX, 7.5, documento="https://example.org/anexo.pdf"))
    assert descarte(result, MAX).motivo == "conflicto"


def test_accumulative_fields_keep_every_distinct_value():
    otros = "/requisitos/otros"
    result = resolve(
        res(otros, "IVA no incluido."),
        res(otros, "iva no  incluido"),
        res(otros, "Gastos de comunidad no incluidos"),
        res(otros, "Poco claro", 0.6),
        res(NO, "empadronamiento"),
        res(NO, "edad"),
    )
    assert [c.valor for c in result.campos if c.campo == otros] == [
        "Gastos de comunidad no incluidos",
        "IVA no incluido.",
    ]
    assert [c.valor for c in result.campos if c.campo == NO] == ["edad", "empadronamiento"]
    assert result.descartes == ()


def test_tables_take_priority_over_text_for_tipologias():
    table = res("/tipologias", [tipologia(2, 600)], 0.85, metodo="pdf_tabla")
    text = res("/tipologias", [tipologia(2, 650)], 0.99)
    result = resolve(text, table)
    assert result.valor("/tipologias") == [tipologia(2, 600)]
    assert result.descartes == ()


def test_unreadable_table_does_not_hide_the_text():
    table = res("/tipologias", [tipologia(2, 600)], 0.4, metodo="pdf_tabla")
    assert resolve(table, res("/tipologias", [tipologia(2, 650)])).valor("/tipologias") == [tipologia(2, 650)]


def test_two_tables_that_disagree_conflict_and_row_order_is_irrelevant():
    rows = [tipologia(1, 500), tipologia(2, 600)]
    same = resolve(
        res("/tipologias", rows, metodo="pdf_tabla"),
        res("/tipologias", rows[::-1], metodo="pdf_tabla", pagina=2),
    )
    assert len(same.campos) == 1 and same.descartes == ()
    different = resolve(
        res("/tipologias", rows, metodo="pdf_tabla"),
        res("/tipologias", [tipologia(1, 550)], metodo="pdf_tabla"),
    )
    assert descarte(different, "/tipologias").motivo == "conflicto"


def test_incoherent_rents_leave_the_whole_table_under_the_threshold():
    table = res("/tipologias", [tipologia(1, 700), tipologia(3, 600)], 0.95, metodo="pdf_tabla")
    result = resolve(table, res("/tipologias", [tipologia(1, 700)], 0.9))
    assert result.valor("/tipologias") is None  # the text does not take over a suspicious table
    assert descarte(result, "/tipologias").motivo == "no_encontrado"
    assert descarte(result, "/tipologias").candidatos[0].confianza < 0.8
    assert any("incoherentes" in a for a in result.advertencias)


def test_annex_results_stay_separate_and_can_conflict():
    garage = {"disponibilidad": "incluido", "precio_mensual_eur": None}
    result = resolve(res(CAMPO_GARAJE, garage), res("/tipologias", [tipologia(2, 600)]))
    assert result.valor(CAMPO_GARAJE) == garage
    assert result.valor("/tipologias") == [tipologia(2, 600)]
    other = {"disponibilidad": "opcional", "precio_mensual_eur": 40}
    clash = resolve(res(CAMPO_GARAJE, garage), res(CAMPO_GARAJE, other))
    assert descarte(clash, CAMPO_GARAJE).motivo == "conflicto"


def test_implausible_values_are_dropped():
    result = resolve(res("/requisitos/tasa_esfuerzo_max", 0.9))
    assert result.campos == ()
    assert descarte(result, "/requisitos/tasa_esfuerzo_max").motivo == "fuera_de_rango"
    assert result.advertencias

    # A plausible rival is not contradicted by an implausible one.
    result = resolve(res(MAX, 55), res(MAX, 5.5))
    assert result.valor(MAX) == 5.5 and result.descartes == ()


def test_unsupported_field_is_ignored_with_a_warning():
    result = resolve(res("/viviendas_total", 10))
    assert result.campos == () and result.descartes == ()
    assert "/viviendas_total" in result.advertencias[0]


@pytest.mark.parametrize(
    ("menor", "mayor", "a", "b"),
    [
        ("/fechas/inscripcion_inicio", "/fechas/inscripcion_fin", "2026-12-10", "2026-12-01"),
        (MIN, MAX, 5.5, 5.5),
    ],
)
def test_incoherent_pairs_are_both_rejected(menor, mayor, a, b):
    result = resolve(res(menor, a), res(mayor, b))
    assert result.campos == ()
    for campo in (menor, mayor):
        assert descarte(result, campo).motivo == "conflicto"
        assert [c.valor for c in descarte(result, campo).candidatos] == [a, b]


def test_value_both_found_and_declared_not_required_gives_neither():
    result = resolve(res(EMP, EMPADRONAMIENTO), res(NO, "empadronamiento"), res(NO, "edad"))
    assert [c.valor for c in result.campos] == ["edad"]
    conflict = descarte(result, EMP)
    assert conflict.motivo == "conflicto"
    assert [c.valor for c in conflict.candidatos] == [EMPADRONAMIENTO, "empadronamiento"]


def test_weakly_seen_value_still_contradicts_the_negation():
    result = resolve(res(EMP, EMPADRONAMIENTO, 0.6), res(NO, "empadronamiento"))
    assert result.campos == ()
    assert descarte(result, EMP).motivo == "conflicto"


def test_denied_income_bound_also_rejects_the_members_table():
    table = [{"miembros_desde": 1, "miembros_hasta": None, "min_iprem": 2.0, "max_iprem": 5.5}]
    result = resolve(res("/requisitos/ingresos_por_miembros", table), res(NO, "ingresos_min_iprem"))
    assert result.campos == ()
    assert descarte(result, "/requisitos/ingresos_por_miembros").motivo == "conflicto"


def test_output_does_not_depend_on_candidate_order():
    candidatos = [
        res(MAX, 5.5),
        res(MAX, 7.5),
        res(MIN, 2.5, 0.9),
        res(MIN, 2.5, 0.9, regla="REG-A", pagina=3),
        res("/requisitos/otros", "B"),
        res("/requisitos/otros", "A"),
        res("/tipologias", [tipologia(2, 600)], metodo="pdf_tabla"),
        res("/fechas/sorteo", "2001-01-01"),
    ]
    expected = pipeline.resolver(candidatos, CTX)
    for seed in range(10):
        shuffled = random.Random(seed).sample(candidatos, len(candidatos))
        result = pipeline.resolver(shuffled, CTX)
        assert (result.campos, result.descartes) == (expected.campos, expected.descartes)


def test_a_failing_extractor_is_a_warning_and_the_rest_still_run():
    doc = Document.desde_parrafos([["texto"]], url=URL)
    candidatos, advertencias = pipeline.extraer_candidatos(
        doc,
        CTX,
        [
            Fake(nombre="roto", error=RuntimeError("boom")),
            Fake(replace(res(MAX, 5.5), documento=None)),
        ],
    )
    assert [(c.valor, c.documento) for c in candidatos] == [(5.5, URL)]
    assert len(advertencias) == 1 and "roto" in advertencias[0] and "boom" in advertencias[0]


def fake_preprocess(monkeypatch, preparar):
    module = types.ModuleType("vpo.extraction.preprocess")
    module.preparar = preparar
    monkeypatch.setitem(sys.modules, module.__name__, module)


def test_extraer_preprocesses_extracts_and_resolves(monkeypatch):
    prepared = Document.desde_parrafos([["texto"]], url=URL)
    fake_preprocess(monkeypatch, lambda doc: prepared)
    raw = Document(URL, "pdf", "0" * 64, (Page(1, "texto"),))
    result = pipeline.extraer(raw, CTX, [Fake(res(MAX, 5.5)), Fake(error=ValueError("x"), nombre="roto")])
    assert result.valor(MAX) == 5.5
    assert not result.necesita_ocr
    assert "roto" in result.advertencias[0]


def test_scanned_document_yields_discards_for_the_key_fields(monkeypatch):
    fake_preprocess(monkeypatch, lambda doc: doc)
    scanned = Document(URL, "pdf", "0" * 64, (Page(1, ""),), necesita_ocr=True)
    extractor = Fake(res(MAX, 5.5))
    result = pipeline.extraer(scanned, CTX, [extractor])
    assert result.necesita_ocr and result.campos == ()
    assert [(d.campo, d.motivo) for d in result.descartes] == [
        (EMP, "pdf_escaneado"),
        (MAX, "pdf_escaneado"),
        ("/tipologias", "pdf_escaneado"),
    ]
    assert pipeline.extraer_candidatos(scanned, CTX, [extractor]) == ([], [])


def test_scanned_discards_skip_what_another_document_resolved():
    result = resolve(res(MAX, 5.5), res(NO, "empadronamiento"), necesita_ocr=True)
    assert [d.campo for d in result.descartes] == ["/tipologias"]
