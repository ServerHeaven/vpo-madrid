"""EMSV Getafe adapter against trimmed copies of the real pages. No network."""

from pathlib import Path

import pytest
from conftest import DATA_DIR, build_promo, validate_promo

from vpo.core.hashing import html_fragment_text
from vpo.core.jsonio import read_json
from vpo.core.normalize import Municipios
from vpo.sources.base import DocumentoRef, FetchError, Ficha, ListingError, Response
from vpo.sources.emsv_getafe import EmsvGetafeAdapter

TESTS = Path(__file__).parent
HTML = TESTS / "fixtures" / "html"
GOLDEN = TESTS / "golden" / "html" / "emsv_getafe.json"
LISTING_URL = "https://emsvgetafe.org/promociones/"
FICHA_URL = "https://emsvgetafe.org/promocion/promocionarrendamiento-511/"
PAGES = {
    LISTING_URL: "emsv_getafe_listado.html",
    FICHA_URL: "emsv_getafe_ficha_arrendamiento_511.html",
}
CONFIG = {
    "id": "emsv-getafe",
    "url": LISTING_URL,
    "operador": {"id": "emsv-getafe", "nombre": "EMSV Getafe", "tipo": "publico_municipal"},
}
BASES = DocumentoRef(
    "https://emsvgetafe.org/wp-content/uploads/2025/07/BASES-REGULADORAS-y-Anexo-Sorteo.pdf",
    "BASES REGULADORAS DE ADJUDICACION Y BASES DEL SORTEO",
    True,
)


def page(url: str) -> str:
    return (HTML / PAGES[url]).read_text(encoding="utf-8")


def edit(url: str, old: str, new: str, count: int = 1) -> str:
    text = page(url)
    assert old in text, old
    return text.replace(old, new, count)


class FakeFetcher:
    def __init__(self, changes: dict[str, str] | None = None) -> None:
        self.changes = changes or {}
        self.requests: list[str] = []

    def get(self, url: str) -> Response:
        self.requests.append(url)
        if url in self.changes:
            text = self.changes[url]
        elif url in PAGES:
            text = page(url)
        else:
            raise FetchError(url)
        return Response(url, url, 200, text.encode("utf-8"), "utf-8", None, None)


@pytest.fixture
def adapter() -> EmsvGetafeAdapter:
    return EmsvGetafeAdapter(CONFIG, Municipios.load(DATA_DIR))


def parse(adapter, ficha_html: str | None = None):
    changes = {} if ficha_html is None else {FICHA_URL: ficha_html}
    [ficha] = adapter.listar(FakeFetcher())
    return adapter.parsear_ficha(ficha, FakeFetcher(changes))


# -- listing ----------------------------------------------------------------------------------


def test_listing_has_the_rental_promotion_but_no_services_or_sales(adapter):
    assert adapter.listar(FakeFetcher()) == [Ficha(FICHA_URL, "Promoción Arrendamiento 5.1.1")]


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("<h3>Alquiler de viviendas</h3>", "<h3>Alquiler</h3>"),
        ('class="hogares-lst"', 'class="otra"'),
        ("/promociones/vivienda-abierta/", "/promociones/alquiler-joven-2027/"),  # unknown entry
        ("/promocion/promocionarrendamiento-511/", "/promocion/promocionarrendamiento-511/listado.pdf"),
        ("https://emsvgetafe.org/promocion/promocionarrendamiento-511/", "https://example.org/promocion/x/"),
    ],
)
def test_listing_raises_instead_of_returning_a_partial_list(adapter, old, new):
    with pytest.raises(ListingError):
        adapter.listar(FakeFetcher({LISTING_URL: edit(LISTING_URL, old, new)}))


# -- ficha ------------------------------------------------------------------------------------


def test_golden(adapter):
    parsed = parse(adapter)

    assert {FICHA_URL: {"datos": parsed.datos, "procedencia": parsed.procedencia}} == read_json(GOLDEN)


def test_output_is_valid_deterministic_and_traced(adapter):
    parsed = parse(adapter)
    meta = build_promo()["meta"] | {"campos_pendientes": [], "procedencia": parsed.procedencia}

    assert validate_promo(parsed.datos | {"id": "emsv-getafe-getafe-prueba", "meta": meta}) == []
    assert parse(adapter) == parsed
    assert all(item["evidencia"] for item in parsed.procedencia.values())


def test_what_the_page_does_not_say_stays_null(adapter):
    datos = parse(adapter).datos

    assert (datos["regimen"], datos["viviendas_total"], datos["tipologias"]) == ("DESCONOCIDO", None, [])
    assert (datos["ubicacion"]["direccion"], datos["enlaces"]["solicitud"]) == (None, None)
    requisitos = datos["requisitos"]
    assert requisitos["edad"] is None  # it differs between the two lottery groups
    assert requisitos["ingresos_max_iprem"] is None and requisitos["no_titular_vivienda"] is None
    assert requisitos["empadronamiento"]["anios_min"] is None
    assert "Grupo 2: 22 VIVIENDAS DE 18 A 35 AÑOS" in requisitos["otros"]


def test_without_the_exclusion_sentence_the_work_alternative_is_unknown(adapter):
    changed = edit(FICHA_URL, ", no permitiéndose otras opciones.", ".", count=2)

    empadronamiento = parse(adapter, changed).datos["requisitos"]["empadronamiento"]

    assert empadronamiento["alternativa_trabajo"] is None
    assert empadronamiento["ininterrumpido"] is True


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("no permitiéndose otras opciones.", "salvo excepciones."),  # an unknown qualifier
        ("requisito necesario estar empadronado", "preferible estar empadronado"),
    ],
)
def test_reworded_registration_condition_stays_null(adapter, old, new):
    changed = edit(FICHA_URL, old, new, count=2)

    assert parse(adapter, changed).datos["requisitos"]["empadronamiento"] is None


def test_without_a_result_the_lists_still_show_the_lottery_phase(adapter):
    changed = edit(FICHA_URL, "RESULTADO DEL SORTEO 19/01/2026", "PLANOS")

    datos = parse(adapter, changed).datos

    assert (datos["estado"], datos["fechas"]["sorteo"]) == ("sorteo_adjudicacion", None)


def test_a_page_with_only_bases_has_unknown_state(adapter):
    text = edit(FICHA_URL, "RESULTADO DEL SORTEO 19/01/2026", "PLANOS")
    start = text.index('<section class="grupo-cont-sec')
    end = text.index('<section class="faqs-sc-container">')

    parsed = parse(adapter, text[:start] + text[end:])

    assert parsed.datos["estado"] == "desconocido"
    assert "/estado" not in parsed.procedencia


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('class="sorito-sec"', 'class="otra"', "formato"),
        ("<h1>Promoción Arrendamiento 5.1.1</h1>", "", "formato"),
        ("gastos ordinarios de comunidad", "gastos de la compraventa", "venta"),
    ],
)
def test_an_unexpected_ficha_fails_that_promotion(adapter, old, new, message):
    with pytest.raises(ValueError, match=message):
        parse(adapter, edit(FICHA_URL, old, new))


# -- documents and change detection -----------------------------------------------------------


def test_only_the_bases_are_a_document_and_lists_are_never_requested(adapter):
    http = FakeFetcher()
    [ficha] = adapter.listar(http)
    adapter.parsear_ficha(ficha, http)

    assert adapter.documentos(ficha, http) == [BASES]
    assert set(http.requests) == {LISTING_URL, FICHA_URL}


def test_a_private_path_is_never_a_document(adapter):
    changed = edit(FICHA_URL, "uploads/2025/07/BASES-REGULADORAS", "uploads/no-index/BASES-REGULADORAS")

    assert adapter.documentos(Ficha(FICHA_URL, "x"), FakeFetcher({FICHA_URL: changed})) == []


@pytest.mark.parametrize("url", list(PAGES))
def test_hash_selector_covers_the_content(adapter, url):
    assert len(html_fragment_text(page(url), adapter.selector_hash())) > 200
