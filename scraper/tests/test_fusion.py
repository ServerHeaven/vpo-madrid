"""Merging PDF results into the HTML data. Everything here is synthetic."""

import copy

from conftest import build_promo, validate_promo
from vpo.extraction.base import CAMPO_GARAJE, CAMPO_TRASTERO, ExtractionResult, FieldResult
from vpo.extraction.fusion import aplicar
from vpo.sources.base import anejo_desconocido, fechas_desconocidas, requisitos_desconocidos
from vpo.sources.base import tipologia as tipologia_vacia

URL = "https://example.org/bases.pdf"
HTML_ENTRY = {
    "metodo": "html",
    "confianza": 0.9,
    "documento": "https://example.org/promo",
    "pagina": None,
    "evidencia": "texto de la web",
    "regla": None,
}
EMPADRONAMIENTO = {
    "ambito": "municipio",
    "municipio_ine": "28079",
    "anios_min": 3,
    "ininterrumpido": True,
    "alternativa_trabajo": None,
}
TRAMOS = [{"miembros_desde": 1, "miembros_hasta": None, "min_iprem": None, "max_iprem": 5.5}]


def datos(tipologias=(), requisitos=None, fechas=None):
    promo = build_promo()
    del promo["id"], promo["meta"]
    promo["tipologias"] = list(tipologias)
    promo["requisitos"] = requisitos_desconocidos() | (requisitos or {})
    promo["fechas"] = fechas_desconocidas() | (fechas or {})
    return promo


def html(dormitorios, **changes):
    return tipologia_vacia(dormitorios) | changes


def fila(dormitorios, renta, superficie=None, unidades=None, **changes):
    return tipologia_vacia(dormitorios) | {
        "renta_mensual_eur": renta,
        "superficie_util_m2": superficie,
        "num_viviendas": unidades,
    } | changes


def anejo(disponibilidad, precio=None):
    return {"disponibilidad": disponibilidad, "precio_mensual_eur": precio}


def res(campo, valor, metodo="pdf_texto", confianza=0.9):
    return FieldResult(campo, valor, confianza, 2, "cita del PDF", "REG-TEST", metodo, URL)


def merge(original, *campos, procedencia=None):
    procedencia = procedencia or {}
    before = copy.deepcopy((original, procedencia))
    merged, cited, descartes = aplicar(original, procedencia, ExtractionResult(campos=campos))
    assert (original, procedencia) == before, "inputs must not be mutated"
    base = build_promo()
    promo = merged | {"id": base["id"], "meta": base["meta"] | {"procedencia": cited}}
    assert validate_promo(promo) == []
    return merged, cited, descartes


def test_pdf_values_fill_unknowns_with_their_provenance():
    merged, cited, descartes = merge(
        datos(),
        res("/requisitos/ingresos_max_iprem", 5.5),
        res("/requisitos/empadronamiento", EMPADRONAMIENTO),
        res("/fechas/sorteo", "2026-12-01"),
        res("/tipologias", [fila(2, 600.0)], "pdf_tabla"),
    )
    assert merged["requisitos"]["ingresos_max_iprem"] == 5.5
    assert merged["requisitos"]["empadronamiento"] == EMPADRONAMIENTO
    assert merged["fechas"]["sorteo"] == "2026-12-01"
    assert merged["tipologias"] == [fila(2, 600.0)]
    assert cited["/requisitos/ingresos_max_iprem"] == {
        "metodo": "pdf_texto",
        "confianza": 0.9,
        "documento": URL,
        "pagina": 2,
        "evidencia": "cita del PDF",
        "regla": "REG-TEST",
    }
    assert cited["/tipologias"]["metodo"] == "pdf_tabla"
    assert set(cited) == {
        "/requisitos/ingresos_max_iprem",
        "/requisitos/empadronamiento",
        "/fechas/sorteo",
        "/tipologias",
    }
    assert descartes == []


def test_html_values_are_never_overwritten():
    original = datos(
        [html(2, renta_mensual_eur=550.0)],
        {"ingresos_max_iprem": 4.5},
        {"sorteo": "2026-12-05"},
    )
    provenance = {"/requisitos/ingresos_max_iprem": HTML_ENTRY}
    merged, cited, descartes = merge(
        original,
        res("/requisitos/ingresos_max_iprem", 5.5),
        res("/fechas/sorteo", "2026-12-01"),
        res("/tipologias", [fila(2, 600.0)]),
        procedencia=provenance,
    )
    assert merged == original
    assert cited == provenance
    assert descartes == []


def test_html_tipologias_are_enriched_by_dormitorios():
    original = datos([html(1, num_viviendas=3), html(2, num_viviendas=30), html(3)])
    rows = [fila(1, 450.0, 40.0, 3), fila(2, 600.0, 60.0, 20), fila(2, 650.0, 70.0, 10)]
    merged, cited, descartes = merge(
        original, res("/tipologias", rows, "pdf_tabla"), procedencia={"/tipologias": HTML_ENTRY}
    )
    one, two, three = merged["tipologias"]
    keys = ("renta_mensual_eur", "renta_mensual_max_eur", "superficie_util_m2")
    assert [one[k] for k in keys] == [450.0, None, 40.0]
    assert [two[k] for k in keys] == [600.0, 650.0, None]
    assert two["num_viviendas"] == 30
    assert three == html(3)
    assert cited["/tipologias"] == HTML_ENTRY
    assert cited["/tipologias/1/renta_mensual_max_eur"]["metodo"] == "pdf_tabla"
    assert "/tipologias/1/num_viviendas" not in cited
    assert descartes == []


def test_a_row_without_rent_leaves_the_range_unknown():
    merged, _, _ = merge(datos([html(2)]), res("/tipologias", [fila(2, 600.0), fila(2, None, 70.0)]))
    assert merged["tipologias"][0]["renta_mensual_eur"] is None


def test_unknown_dormitorios_in_the_pdf_attach_nothing_and_conflict():
    for rows in ([fila(1, 450.0), fila(4, 900.0)], [fila(1, 450.0), fila(None, 500.0, 50.0)]):
        original = datos([html(1), html(2)])
        result = res("/tipologias", rows)
        merged, _, descartes = merge(original, result)
        assert merged == original
        assert [(d.campo, d.motivo, d.candidatos) for d in descartes] == [("/tipologias", "conflicto", (result,))]


def test_ambiguous_or_contradicted_typologies_stay_null():
    # Two HTML entries with the same dormitorios: no way to tell which row is which.
    original = datos([html(2, superficie_util_m2=60.0), html(2, superficie_util_m2=80.0)])
    merged, _, descartes = merge(original, res("/tipologias", [fila(2, 600.0)]))
    assert merged == original and descartes[0].motivo == "conflicto"

    for existing in (html(2, num_viviendas=50), html(2, superficie_util_m2=80.0)):
        original = datos([existing])
        merged, _, descartes = merge(original, res("/tipologias", [fila(2, 600.0, 60.0, 10)]))
        assert merged == original and descartes[0].campo == "/tipologias"


def test_annex_fills_only_unknown_availability():
    original = datos([html(1), html(2, garaje=anejo("no")), html(3, garaje=anejo("desconocido", 30.0))])
    garage, storage = res(CAMPO_GARAJE, anejo("opcional", 50.0)), res(CAMPO_TRASTERO, anejo("no"))
    merged, cited, _ = merge(original, garage, storage)
    assert [t["garaje"] for t in merged["tipologias"]] == [
        anejo("opcional", 50.0),
        anejo("no"),
        anejo("desconocido", 30.0),  # a different price: not the same thing
    ]
    assert all(t["trastero"] == anejo("no") for t in merged["tipologias"])
    assert "/tipologias/0/garaje" in cited and "/tipologias/1/garaje" not in cited


def test_annex_applies_to_pdf_tipologias_and_respects_their_rows():
    rows = [fila(1, 450.0), fila(2, 600.0, garaje=anejo("incluido"))]
    merged, _, _ = merge(datos(), res("/tipologias", rows), res(CAMPO_GARAJE, anejo("opcional")))
    assert [t["garaje"] for t in merged["tipologias"]] == [anejo("opcional"), anejo("incluido")]

    # Rows of one typology disagree: the general statement does not settle it.
    rows = [fila(2, 600.0, garaje=anejo("incluido")), fila(2, 650.0, garaje=anejo("opcional"))]
    merged, _, _ = merge(datos([html(2)]), res("/tipologias", rows), res(CAMPO_GARAJE, anejo("opcional")))
    assert merged["tipologias"][0]["garaje"] == anejo_desconocido()


def test_otros_are_appended_without_duplicates():
    original = datos(requisitos={"otros": ["IVA no incluido."]})
    merged, cited, _ = merge(
        original,
        res("/requisitos/otros", "iva no incluido"),
        res("/requisitos/otros", "Gastos de comunidad aparte"),
        procedencia={"/requisitos/otros": HTML_ENTRY},
    )
    assert merged["requisitos"]["otros"] == ["IVA no incluido.", "Gastos de comunidad aparte"]
    assert cited["/requisitos/otros"] == HTML_ENTRY
    assert cited["/requisitos/otros/1"]["metodo"] == "pdf_texto"

    merged, cited, _ = merge(datos(), res("/requisitos/otros", "A"), res("/requisitos/otros", "B"))
    assert merged["requisitos"]["otros"] == ["A", "B"]
    assert set(cited) == {"/requisitos/otros", "/requisitos/otros/1"}


def test_members_table_keeps_out_contradicting_flat_values():
    flat = res("/requisitos/ingresos_max_iprem", 7.5)
    merged, _, descartes = merge(
        datos(),
        flat,
        res("/requisitos/ingresos_min_iprem", 2.0),
        res("/requisitos/ingresos_por_miembros", TRAMOS, "pdf_tabla"),
    )
    assert merged["requisitos"]["ingresos_por_miembros"] == TRAMOS
    assert merged["requisitos"]["ingresos_max_iprem"] is None
    assert merged["requisitos"]["ingresos_min_iprem"] == 2.0  # the table says nothing about it
    assert [(d.campo, d.candidatos) for d in descartes] == [("/requisitos/ingresos_max_iprem", (flat,))]


def test_members_table_that_contradicts_the_html_is_not_added():
    original = datos(requisitos={"ingresos_max_iprem": 4.5})
    merged, _, descartes = merge(original, res("/requisitos/ingresos_por_miembros", TRAMOS))
    assert merged == original
    assert descartes[0].campo == "/requisitos/ingresos_por_miembros"


def test_pdf_values_incoherent_with_the_html_are_not_added():
    original = datos(requisitos={"ingresos_max_iprem": 3.0}, fechas={"inscripcion_fin": "2026-12-01"})
    merged, _, descartes = merge(
        original, res("/requisitos/ingresos_min_iprem", 3.5), res("/fechas/inscripcion_inicio", "2026-12-02")
    )
    assert merged == original
    assert [d.campo for d in descartes] == ["/fechas/inscripcion_inicio", "/requisitos/ingresos_min_iprem"]


def test_not_required_names_and_values_never_coexist():
    original = datos(requisitos={"empadronamiento": EMPADRONAMIENTO, "no_exigidos": ["edad"]})
    age = res("/requisitos/edad", {"min": 18, "max": None, "tipo": "requisito"})
    merged, _, descartes = merge(
        original, age, res("/requisitos/no_exigidos", "empadronamiento"), res("/requisitos/no_exigidos", "edad")
    )
    assert merged == original
    assert [(d.campo, d.candidatos) for d in descartes] == [("/requisitos/edad", (age,))]

    merged, cited, _ = merge(datos(), res("/requisitos/no_exigidos", "empadronamiento"))
    assert merged["requisitos"]["no_exigidos"] == ["empadronamiento"]
    assert cited["/requisitos/no_exigidos"]["regla"] == "REG-TEST"
