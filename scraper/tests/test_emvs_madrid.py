"""EMVS adapter against trimmed copies of the real pages (see fixtures/FUENTES.md). No network."""

from pathlib import Path

import pytest
from conftest import DATA_DIR, build_promo, validate_promo

from vpo.core.hashing import html_fragment_text
from vpo.core.normalize import Municipios
from vpo.sources.base import DocumentoRef, FetchError, Ficha, ListingError, Response
from vpo.sources.emvs_madrid import LOTTERY_URL, EmvsMadridAdapter

HTML = Path(__file__).parent / "fixtures" / "html"
LISTING_URL = "https://www.emvs.es/nuestras-promociones/en-proyecto-y-obra"
FICHAS = "https://www.emvs.es/Proyectos/Promociones/Paginas/"
PAGES = {
    LISTING_URL: "emvs_listado_en_proyecto_y_obra.html",
    LOTTERY_URL: "emvs_sorteo.html",
    FICHAS + "IL1.aspx": "emvs_ficha_il1.html",
    FICHAS + "AF6.aspx": "emvs_ficha_af6.html",
    FICHAS + "CANAV10.aspx": "emvs_ficha_canav10.html",
    FICHAS + "V71.aspx": "emvs_ficha_v71.html",
}
CONFIG = {
    "id": "emvs-madrid",
    "url": LISTING_URL,
    "operador": {"id": "emvs-madrid", "nombre": "EMVS Madrid", "tipo": "publico_municipal"},
}
CLOSED = "El plazo de inscripción ha finalizado el día 11 de junio de 2026."


def page(url: str) -> str:
    return (HTML / PAGES[url]).read_text(encoding="utf-8")


def edit(url: str, old: str, new: str) -> str:
    text = page(url)
    assert old in text, old
    return text.replace(old, new)


def uncomment_button(text: str) -> str:
    start = text.index('<!-- <div class="bloqBorde')
    end = text.index("-->", start)
    return text[:start] + text[start + 4 : end] + text[end + 3 :]


class FakeFetcher:
    def __init__(self, changes: dict[str, str] | None = None) -> None:
        self.changes = changes or {}

    def get(self, url: str) -> Response:
        if url in self.changes:
            text = self.changes[url]
        elif url in PAGES:
            text = page(url)
        else:
            raise FetchError(url)
        return Response(url, url, 200, text.encode("utf-8"), "utf-8", None, None)


@pytest.fixture
def adapter() -> EmvsMadridAdapter:
    return EmvsMadridAdapter(CONFIG, Municipios.load(DATA_DIR))


def parse(adapter, code: str, changes: dict[str, str] | None = None):
    http = FakeFetcher(changes)
    ficha = next(f for f in adapter.listar(http) if f.url == f"{FICHAS}{code}.aspx")
    return adapter.parsear_ficha(ficha, http)


def types(datos: dict) -> list[tuple]:
    return [(t["dormitorios"], t["num_viviendas"]) for t in datos["tipologias"]]


# -- listing ----------------------------------------------------------------------------------


def test_listing_has_the_works_promotions_plus_the_lottery(adapter):
    fichas = adapter.listar(FakeFetcher())

    assert [f.url.removeprefix(FICHAS).removesuffix(".aspx") for f in fichas] == (
        "AF6 BA1 CANAV07 CANAV10 C28 C35 E6 IL2 MCALDERON NSA3 ON3 PD3 PD4 PD5 VC4 V71 V72 IL1".split()
    )
    assert fichas[0] == Ficha(FICHAS + "AF6.aspx", "Arroyo Fresno 6", {"viviendas_listado": 36})
    assert fichas[-1] == Ficha(FICHAS + "IL1.aspx", "Iberia Loreto 1", {"sorteo": True})
    assert adapter.listar(FakeFetcher()) == fichas


def test_ficha_url_does_not_depend_on_how_the_link_is_written(adapter):
    changed = edit(
        LISTING_URL,
        'href="/Proyectos/Promociones/Paginas/AF6.aspx"',
        'href="http://emvs.es/proyectos/promociones/paginas/af6.aspx?x=1#top"',
    )

    assert adapter.listar(FakeFetcher({LISTING_URL: changed}))[0].url == FICHAS + "AF6.aspx"


@pytest.mark.parametrize(
    ("url", "old", "new"),
    [
        (LISTING_URL, 'id="MenuBloquesImg"', 'id="Otro"'),
        (LISTING_URL, "<h1>Promociones en proyecto y obra</h1>", "<h1>Mantenimiento</h1>"),
        (LISTING_URL, "/Proyectos/Promociones/Paginas/BA1.aspx", "/otra-cosa"),
        (LISTING_URL, "/Proyectos/Promociones/Paginas/BA1.aspx", "/Proyectos/Promociones/Paginas/AF6.aspx"),
        (LOTTERY_URL, "<h1>Sorteo Iberia Loreto</h1>", "<h1>Mantenimiento</h1>"),
        (LOTTERY_URL, 'href="/Proyectos/Promociones/Paginas/IL1.aspx"', 'href="/Proyectos"'),
        (LOTTERY_URL, "<h2>Galería interior", '<a href="/Proyectos/Promociones/Paginas/IL2.aspx">IL2</a><h2>'),
    ],
)
def test_listing_raises_instead_of_returning_a_partial_list(adapter, url, old, new):
    with pytest.raises(ListingError):
        adapter.listar(FakeFetcher({url: edit(url, old, new)}))


# -- fichas -----------------------------------------------------------------------------------


@pytest.mark.parametrize("code", ["AF6", "CANAV10", "V71", "IL1"])
def test_output_is_valid_deterministic_and_traced(adapter, code):
    parsed = parse(adapter, code)
    meta = build_promo()["meta"] | {"campos_pendientes": [], "procedencia": parsed.procedencia}

    assert validate_promo(parsed.datos | {"id": "emvs-madrid-madrid-prueba", "meta": meta}) == []
    assert parse(adapter, code) == parsed

    required = {"/estado"}
    if parsed.datos["viviendas_total"] is not None:
        required.add("/viviendas_total")
    if parsed.datos["ubicacion"]["direccion"] is not None:
        required.add("/ubicacion/direccion")
    required |= {f"/requisitos/{k}" for k, v in parsed.datos["requisitos"].items() if v not in (None, [])}
    assert required <= set(parsed.procedencia)
    assert all(entry["evidencia"] for entry in parsed.procedencia.values())


def test_works_ficha(adapter):
    datos = parse(adapter, "AF6").datos

    assert datos["nombre"] == "Arroyo Fresno 6"
    assert (datos["estado"], datos["regimen"], datos["modalidad"]) == ("proxima", "VPPA", "alquiler")
    assert (datos["programa"], datos["fuente_id"]) == ("EMVS_MADRID", "emvs-madrid")
    assert datos["operador"] == CONFIG["operador"]
    assert datos["ubicacion"] == {
        "municipio_ine": "28079",
        "municipio": "Madrid",
        "distrito": "Fuencarral-El Pardo",
        "direccion": "C/ María de Maeztu 26 y 28 (24 y 30 garaje, 22 locales)",
        "lat": None,
        "lon": None,
    }
    assert datos["viviendas_total"] == 36
    assert types(datos) == [(2, 14), (3, 20), (4, 2)]  # "12 + 2 PMR" are all two-bedroom
    assert datos["requisitos"]["edad"] is None and datos["requisitos"]["otros"] == []
    assert set(datos["fechas"].values()) == {None}
    assert datos["enlaces"] == {"oficial": FICHAS + "AF6.aspx", "solicitud": None, "bases": []}


def test_a_type_with_zero_homes_is_dropped(adapter):
    datos = parse(adapter, "CANAV10").datos

    assert datos["viviendas_total"] == 46
    assert types(datos) == [(2, 14), (3, 28), (4, 4)]
    assert datos["regimen"] == "VPPA"


def test_unknown_category_and_area_that_is_not_a_district(adapter):
    parsed = parse(adapter, "V71")

    assert parsed.datos["regimen"] == "DESCONOCIDO"
    assert parsed.datos["ubicacion"]["distrito"] is None
    assert parsed.datos["ubicacion"]["direccion"] == "C/ José Gutiérrez Maroto, 2"
    assert types(parsed.datos) == [(2, 26), (3, 20)]
    assert "/modalidad" not in parsed.procedencia  # the page never says it is for rent
    assert "/regimen" not in parsed.procedencia


def test_district_without_a_period_before_the_street(adapter):
    url = FICHAS + "V71.aspx"
    changed = edit(url, "Ensanche de Vallecas. C/", "Vicálvaro C/")

    ubicacion = parse(adapter, "V71", {url: changed}).datos["ubicacion"]

    assert (ubicacion["distrito"], ubicacion["direccion"]) == ("Vicálvaro", "C/ José Gutiérrez Maroto, 2")


def test_unit_counts_that_do_not_add_up_are_dropped(adapter):
    url = FICHAS + "V71.aspx"
    datos = parse(adapter, "V71", {url: edit(url, "(26+20)", "(26+21)")}).datos

    assert types(datos) == [(2, None), (3, None)]


def test_contradicting_totals_give_null(adapter):
    url = FICHAS + "AF6.aspx"
    datos = parse(adapter, "AF6", {url: edit(url, "36 / 76 / 6", "37 / 76 / 6")}).datos

    assert datos["viviendas_total"] is None
    assert types(datos) == [(2, None), (3, None), (4, None)]


def test_a_sale_mention_is_raised_not_hidden(adapter):
    url = FICHAS + "V71.aspx"
    changed = edit(url, "garaje subterráneo", "garaje subterráneo, viviendas en venta")

    with pytest.raises(ValueError, match="venta"):
        parse(adapter, "V71", {url: changed})


def test_an_unexpected_page_fails_that_promotion(adapter):
    url = FICHAS + "AF6.aspx"

    with pytest.raises(ValueError, match="formato"):
        parse(adapter, "AF6", {url: edit(url, 'id="FichaPromocion"', 'id="Otro"')})


# -- lottery ----------------------------------------------------------------------------------


def test_lottery_promotion(adapter):
    parsed = parse(adapter, "IL1")
    datos = parsed.datos

    assert datos["nombre"] == "Iberia Loreto 1"
    assert (datos["estado"], datos["regimen"], datos["viviendas_total"]) == ("inscripcion_cerrada", "VPPA", 52)
    assert datos["fechas"]["inscripcion_fin"] == "2026-06-11"
    assert datos["ubicacion"]["distrito"] == "Barajas"
    assert datos["ubicacion"]["direccion"] == "C/ Venus, 5-7"
    assert types(datos) == [(2, 16), (3, 36)]
    assert datos["enlaces"] == {"oficial": LOTTERY_URL, "solicitud": None, "bases": []}
    assert datos["requisitos"] == {
        "ingresos_min_iprem": 3.5,
        "ingresos_max_iprem": 5.5,
        "ingresos_por_miembros": None,
        "iprem_pagas": None,
        "iprem_ejercicio": 2025,
        "tasa_esfuerzo_max": None,
        "empadronamiento": {
            "ambito": "municipio",
            "municipio_ine": "28079",
            "anios_min": 5,
            "ininterrumpido": None,
            "alternativa_trabajo": None,
        },
        "edad": {"min": 18, "max": 50, "tipo": "requisito"},
        "no_titular_vivienda": True,
        "no_exigidos": [],
        "otros": [
            "Ser español o residente legal en España",
            "No haber sido ninguno de los miembros de la unidad familiar condenado por delitos de "
            "allanamiento de morada o por usurpación de vivienda",
            "No haber sido ninguno de los miembros de la unidad familiar condenado en procedimientos de "
            "desahucio de vivienda en régimen de arrendamiento por impago de rentas",
        ],
    }
    assert parsed.procedencia["/estado"]["evidencia"] == CLOSED
    assert parsed.procedencia["/estado"]["documento"] == LOTTERY_URL


def lottery(adapter, text: str) -> dict:
    return parse(adapter, "IL1", {LOTTERY_URL: text}).datos


def test_the_commented_out_button_does_not_open_registration(adapter):
    assert "Inscríbete</a>" in page(LOTTERY_URL)  # present in the source, inside a comment

    datos = lottery(adapter, edit(LOTTERY_URL, CLOSED, ""))

    assert datos["estado"] == "desconocido"
    assert datos["enlaces"]["solicitud"] is None


def test_a_visible_button_opens_registration(adapter):
    datos = lottery(adapter, uncomment_button(edit(LOTTERY_URL, CLOSED, "")))

    assert datos["estado"] == "inscripcion_abierta"
    assert datos["enlaces"]["solicitud"] == "https://oficinavirtual.emvs.es/"
    assert datos["fechas"]["inscripcion_fin"] is None


def test_contradicting_signs_give_unknown(adapter):
    datos = lottery(adapter, uncomment_button(page(LOTTERY_URL)))

    assert datos["estado"] == "desconocido"
    assert datos["enlaces"]["solicitud"] is None
    assert datos["fechas"]["inscripcion_fin"] is None


def test_a_hidden_notice_is_ignored(adapter):
    changed = edit(LOTTERY_URL, 'class="bloqAviso"', 'class="bloqAviso" style="display:none"')

    assert lottery(adapter, changed)["estado"] == "desconocido"


def test_unrecognised_wording_stays_null_and_readable(adapter):
    changed = edit(LOTTERY_URL, "Tener entre 18 y 50 años", "Tener entre 18 y 50 años, salvo excepciones")

    requisitos = lottery(adapter, changed)["requisitos"]

    assert requisitos["edad"] is None
    assert "Tener entre 18 y 50 años, salvo excepciones" in requisitos["otros"]


def test_contradicting_requirements_stay_null(adapter):
    changed = edit(LOTTERY_URL, '<ul class="destaca">', '<ul class="destaca"><li>Tener entre 18 y 35 años</li>')

    requisitos = lottery(adapter, changed)["requisitos"]

    assert requisitos["edad"] is None
    assert {"Tener entre 18 y 35 años", "Tener entre 18 y 50 años"} <= set(requisitos["otros"])


def test_missing_requirements_list_fails_the_promotion(adapter):
    changed = edit(LOTTERY_URL, "Los requisitos que tienes que cumplir", "Otra cosa")

    with pytest.raises(ValueError, match="requisitos"):
        lottery(adapter, changed)


# -- documents and change detection -----------------------------------------------------------


def test_documents(adapter):
    http = FakeFetcher()
    fichas = {f.url: f for f in adapter.listar(http)}

    assert adapter.documentos(fichas[FICHAS + "IL1.aspx"], http) == [
        DocumentoRef(
            LOTTERY_URL + "/Documents/Bases%20reguladoras%20del%20Programa%20Iberia%20Loreto.pdf",
            "Bases reguladoras del Programa Iberia Loreto",
            True,
        )
    ]
    assert adapter.documentos(fichas[FICHAS + "AF6.aspx"], http) == []


@pytest.mark.parametrize("url", list(PAGES))
def test_hash_selector_covers_the_content_but_not_menus_or_comments(adapter, url):
    text = html_fragment_text(page(url), adapter.selector_hash())

    assert len(text) > 500
    assert "Plan Suma Vivienda" not in text  # side menu
    assert "Inscríbete" not in text
