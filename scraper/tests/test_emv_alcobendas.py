"""EMVIALSA adapter against trimmed copies of the real pages. No network."""

from pathlib import Path

import pytest
from conftest import DATA_DIR, build_promo, validate_promo

from vpo.core.hashing import html_fragment_text
from vpo.core.jsonio import read_json
from vpo.core.normalize import Municipios
from vpo.sources.base import FetchError, Ficha, ListingError, Response, requisitos_desconocidos
from vpo.sources.emv_alcobendas import CALLS_URL, EmvAlcobendasAdapter

TESTS = Path(__file__).parent
HTML = TESTS / "fixtures" / "html"
GOLDEN = TESTS / "golden" / "html" / "emv_alcobendas.json"
LISTING_URL = "https://emvialsa.org/acceso-a-la-vivienda/promociones"
VALDAVIA = "https://emvialsa.org/promocion/en-obra/marques-de-la-valdavia-47"
SALMERON = "https://emvialsa.org/promocion/en-obra/diego-salmeron-4"
VELARDE = "https://emvialsa.org/promocion/en-alquiler-y-cesion-de-uso/velarde-19-av-espana-8"
PAGES = {
    LISTING_URL: "emv_alcobendas_listado.html",
    CALLS_URL: "emv_alcobendas_inscripciones.html",
    VALDAVIA: "emv_alcobendas_ficha_valdavia.html",
    SALMERON: "emv_alcobendas_ficha_salmeron.html",
    VELARDE: "emv_alcobendas_ficha_velarde.html",
}
CONFIG = {
    "id": "emvialsa-alcobendas",
    "url": LISTING_URL,
    "operador": {"id": "emvialsa", "nombre": "EMVIALSA", "tipo": "publico_municipal"},
}
VELARDE_CALL = "Convocatoria promoción viviendas en alquiler calle Velarde, 19 - 21</a></h4>"
CLOSED = '<div class="sppb-article-introtext"><span><strong>PLAZO INSCRIPCIÓN CERRADO</strong></span></div>'


def page(url: str) -> str:
    return (HTML / PAGES[url]).read_text(encoding="utf-8")


def edit(url: str, old: str, new: str, text: str | None = None) -> str:
    text = page(url) if text is None else text
    assert old in text, old
    return text.replace(old, new, 1)


def call_status(title_end: str, status: str) -> str:
    """The registration page with the status of one call replaced."""
    text = page(CALLS_URL)
    start = text.index(title_end)
    cut = text.index(CLOSED, start)
    return text[:cut] + CLOSED.replace("PLAZO INSCRIPCIÓN CERRADO", status) + text[cut + len(CLOSED) :]


def entry(href: str, name: str, summary: str) -> str:
    return (
        f'<div class="sppb-addon-article"><h4><a href="{href}">{name}</a></h4>'
        f'<div class="sppb-article-introtext">{summary}</div></div>'
    )


def added(url: str, before: str, extra: str) -> str:
    """The page with an extra entry just before the first entry containing ``before``."""
    text = page(url)
    cut = text.rindex('<div class="sppb-addon-article-layout ', 0, text.index(before))
    return text[:cut] + extra + text[cut:]


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
def adapter() -> EmvAlcobendasAdapter:
    return EmvAlcobendasAdapter(CONFIG, Municipios.load(DATA_DIR))


def listar(adapter, changes: dict[str, str] | None = None) -> dict[str, Ficha]:
    return {f.url: f for f in adapter.listar(FakeFetcher(changes))}


def parse(adapter, url: str, changes: dict[str, str] | None = None):
    return adapter.parsear_ficha(listar(adapter, changes)[url], FakeFetcher(changes))


# -- listing ----------------------------------------------------------------------------------


def test_listing_has_only_the_rental_works(adapter):
    fichas = adapter.listar(FakeFetcher())

    # Not the "alojamientos dotacionales", the one in planning, nor delivered stock.
    assert [(f.url, f.nombre) for f in fichas] == [
        (VALDAVIA, "Marqués de la Valdavia, 47"),
        (SALMERON, "Diego Salmerón, 4"),
    ]
    assert adapter.listar(FakeFetcher()) == fichas


def test_a_live_call_brings_in_a_rental_from_the_other_tab(adapter):
    changes = {CALLS_URL: call_status(VELARDE_CALL, "PLAZO DE INSCRIPCIÓN ABIERTO")}

    assert list(listar(adapter, changes)) == [VALDAVIA, SALMERON, VELARDE]
    datos = parse(adapter, VELARDE, changes).datos
    assert (datos["estado"], datos["regimen"], datos["viviendas_total"]) == ("inscripcion_abierta", "VPPA", 39)
    assert datos["enlaces"]["solicitud"] == (
        "https://emvialsa.org/convocatoria-inscripcion/convocatoria-promocion-viviendas-en-alquiler-calle-velarde-19-21"
    )
    assert datos["ubicacion"]["direccion"] == "Velarde, 19"
    assert [(t["dormitorios"], t["num_viviendas"]) for t in datos["tipologias"]] == [(1, None), (2, None), (3, None)]


def test_an_unknown_call_status_gives_unknown(adapter):
    changes = {CALLS_URL: call_status(VELARDE_CALL, "Próxima apertura")}

    datos = parse(adapter, VELARDE, changes).datos

    assert datos["estado"] == "desconocido"
    assert datos["enlaces"]["solicitud"] is None


def test_a_closed_call_on_a_work_in_progress(adapter):
    closed = entry("/convocatoria-inscripcion/prueba", "Convocatoria alquiler Diego Salmerón, 4", "PLAZO INSCRIPCIÓN CERRADO")
    changes = {CALLS_URL: added(CALLS_URL, "Miraflores", closed)}

    parsed = parse(adapter, SALMERON, changes)

    assert parsed.datos["estado"] == "inscripcion_cerrada"
    assert parsed.procedencia["/estado"]["documento"] == CALLS_URL


@pytest.mark.parametrize(
    ("url", "old", "new"),
    [
        (LISTING_URL, "<h1 class=\"sppb-addon-title\">Promociones de vivienda</h1>", "<h1>Mantenimiento</h1>"),
        (LISTING_URL, "> En Obra </a>", "> Obras </a>"),
        (LISTING_URL, "> En Alquiler y Cesión de Uso </a>", "> Otra </a>"),
        (LISTING_URL, "41 VPPB, ALQUILER", "41 VPPB"),  # unknown kind: never silently dropped
        (LISTING_URL, "41 VPPB, ALQUILER", "41 VPPB, VENTA Y ALQUILER"),
        (LISTING_URL, "/promocion/en-obra/diego-salmeron-4", "/otra-cosa"),
        (LISTING_URL, "/promocion/en-obra/diego-salmeron-4", "/promocion/en-obra/marques-de-la-valdavia-47"),
        # A full page: more entries could be waiting behind "Leer más".
        (LISTING_URL, "&quot;limit&quot;: &quot;9&quot;", "&quot;limit&quot;: &quot;4&quot;"),
        (LISTING_URL, 'name="sppb-articles-addon-settings"', 'name="otro"'),
        (CALLS_URL, "> CONVOCATORIAS </a>", "> Otra </a>"),
        (CALLS_URL, "&quot;limit&quot;: &quot;9&quot;", "&quot;limit&quot;: &quot;5&quot;"),
    ],
)
def test_listing_raises_instead_of_returning_a_partial_list(adapter, url, old, new):
    with pytest.raises(ListingError):
        adapter.listar(FakeFetcher({url: edit(url, old, new)}))


@pytest.mark.parametrize("title", ["Convocatoria viviendas en alquiler calle Nueva, 1", "Listado de reservas calle Nueva, 1"])
def test_an_open_call_without_a_promotion_raises(adapter, title):
    extra = entry("/convocatoria-inscripcion/nueva", title, "PLAZO DE INSCRIPCIÓN ABIERTO")

    with pytest.raises(ListingError, match="convocatoria"):
        adapter.listar(FakeFetcher({CALLS_URL: added(CALLS_URL, "Miraflores", extra)}))


def test_an_open_sale_call_is_ignored(adapter):
    extra = entry("/convocatoria-inscripcion/nueva", "Venta 1 vivienda calle Nueva, 1", "PLAZO DE INSCRIPCIÓN ABIERTO")

    assert list(listar(adapter, {CALLS_URL: added(CALLS_URL, "Miraflores", extra)})) == [VALDAVIA, SALMERON]


# -- fichas -----------------------------------------------------------------------------------


def test_golden(adapter):
    result = {}
    for url in listar(adapter):
        parsed = parse(adapter, url)
        result[url] = {"datos": parsed.datos, "procedencia": parsed.procedencia}

    assert result == read_json(GOLDEN)


@pytest.mark.parametrize("url", [VALDAVIA, SALMERON])
def test_output_is_valid_deterministic_and_traced(adapter, url):
    parsed = parse(adapter, url)
    meta = build_promo()["meta"] | {"campos_pendientes": [], "procedencia": parsed.procedencia}

    assert validate_promo(parsed.datos | {"id": "emvialsa-alcobendas-prueba", "meta": meta}) == []
    assert parse(adapter, url) == parsed
    assert parsed.datos["requisitos"] == requisitos_desconocidos()
    assert all(item["evidencia"] for item in parsed.procedencia.values())


def test_contradicting_regimen_is_unknown(adapter):
    parsed = parse(adapter, VALDAVIA)  # "VPPB" in the listing, "VPPA" on the ficha

    assert parsed.datos["regimen"] == "DESCONOCIDO"
    assert "/regimen" not in parsed.procedencia
    assert parse(adapter, SALMERON).datos["regimen"] == "VPPL"


def test_contradicting_totals_give_null(adapter):
    changed = edit(SALMERON, "39 / 39 / 39", "40 / 39 / 39")

    datos = parse(adapter, SALMERON, {SALMERON: changed}).datos

    assert datos["viviendas_total"] is None
    assert [t["num_viviendas"] for t in datos["tipologias"]] == [None] * 4


def test_unit_counts_that_do_not_add_up_are_dropped(adapter):
    changed = edit(SALMERON, "8 son de un dormitorio", "9 son de un dormitorio")

    datos = parse(adapter, SALMERON, {SALMERON: changed}).datos

    assert datos["viviendas_total"] == 39
    assert [(t["dormitorios"], t["num_viviendas"]) for t in datos["tipologias"]] == [(n, None) for n in (1, 2, 3, 4)]


def test_unrecognised_programme_gives_no_types(adapter):
    changed = edit(SALMERON, "1D, 2D, 3D, 4D", "De 1 a 4 dormitorios")

    parsed = parse(adapter, SALMERON, {SALMERON: changed})

    assert parsed.datos["tipologias"] == []
    assert "/tipologias" not in parsed.procedencia


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('<h1 class="sppb-addon-title">Diego Salmerón, 4</h1>', "<h1>Otra</h1>", "formato"),
        ("Las viviendas se gestionarán en régimen de arrendamiento.", "Viviendas en venta.", "venta"),
        ("Las viviendas se gestionarán en régimen de arrendamiento.", "Con opción a compra.", "compra"),
    ],
)
def test_an_unexpected_ficha_fails_that_promotion(adapter, old, new, message):
    with pytest.raises(ValueError, match=message):
        parse(adapter, SALMERON, {SALMERON: edit(SALMERON, old, new)})


def test_no_documents(adapter):
    assert adapter.documentos(listar(adapter)[SALMERON], FakeFetcher()) == []


@pytest.mark.parametrize("url", list(PAGES))
def test_hash_selector_covers_the_content(adapter, url):
    assert len(html_fragment_text(page(url), adapter.selector_hash())) > 300
