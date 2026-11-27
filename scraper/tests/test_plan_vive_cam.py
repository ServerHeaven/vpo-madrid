"""Plan Vive adapter against the real page saved in fixtures (no network)."""

from pathlib import Path

import pytest
from selectolax.lexbor import LexborHTMLParser

from conftest import DATA_DIR, validate_promo
from vpo.core.jsonio import read_json
from vpo.core.normalize import Municipios
from vpo.sources.base import ListingError, Response, requisitos_desconocidos
from vpo.sources.plan_vive_cam import PlanViveCamAdapter

TESTS = Path(__file__).parent
HTML = (TESTS / "fixtures" / "html" / "planvive_2026-11-27.html").read_text(encoding="utf-8")
GOLDEN = TESTS / "golden" / "planvive_resumen.json"
CONFIG = next(f for f in read_json(DATA_DIR / "fuentes.json")["fuentes"] if f["id"] == "plan-vive-cam")
PAGE = CONFIG["url"]


class FakeFetcher:
    def __init__(self, html: str) -> None:
        self.html = html
        self.requests: list[str] = []

    def get(self, url: str) -> Response:
        self.requests.append(url)
        return Response(url, url, 200, self.html.encode("utf-8"), "utf-8", None, None)


@pytest.fixture(scope="module")
def adapter() -> PlanViveCamAdapter:
    return PlanViveCamAdapter(CONFIG, Municipios.load(DATA_DIR))


def replace(old: str, new: str, html: str = HTML) -> str:
    assert old in html, old
    return html.replace(old, new, 1)


def listar(adapter, html: str = HTML) -> dict:
    return {f.url.partition("#")[2]: f for f in adapter.listar(FakeFetcher(html))}


def parse(adapter, slug: str, html: str = HTML):
    return adapter.parsear_ficha(listar(adapter, html)[slug], FakeFetcher(""))


def before_news(extra: str) -> str:
    """The page with a new section between the last promotions and the news."""
    news_section = HTML.rfind("<section", 0, HTML.index('id="contenidos-relacionados"'))
    wrapper = HTML.rfind("<div>", 0, news_section)
    return f'{HTML[:wrapper]}<div><section class="paragraph paragraph--type--section">{extra}</section></div>{HTML[wrapper:]}'


def table(name: str, *rows: tuple[str, str]) -> str:
    body = "".join(f"<tr><td><strong>{k}</strong></td><td>{v}</td></tr>" for k, v in rows)
    return f"<table><caption>{name}</caption><tbody>{body}</tbody></table>"


def summarise(url: str, datos: dict) -> dict:
    return {
        "url": url,
        "nombre": datos["nombre"],
        "municipio_ine": datos["ubicacion"]["municipio_ine"],
        "viviendas_total": datos["viviendas_total"],
        "estado": datos["estado"],
        "dormitorios": [t["dormitorios"] for t in datos["tipologias"]],
        "direccion": datos["ubicacion"]["direccion"],
        "solicitud": datos["enlaces"]["solicitud"],
    }


# -- the real page --------------------------------------------------------------------------------


def test_every_block_matches_golden(adapter):
    http = FakeFetcher(HTML)
    fichas = adapter.listar(http)
    summary = [summarise(f.url, adapter.parsear_ficha(f, http).datos) for f in fichas]
    assert http.requests == [PAGE]  # parsear_ficha makes no request
    assert len(fichas) == HTML.count("<caption>") == 26
    assert summary == read_json(GOLDEN)


def test_all_records_are_valid(adapter):
    for slug in listar(adapter):
        result = parse(adapter, slug)
        meta = {
            "primera_deteccion": "2026-11-27",
            "ultima_modificacion": "2026-11-27",
            "activa_en_fuente": True,
            "campos_pendientes": [],
            "campos_override": [],
            "procedencia": result.procedencia,
            "extractor_version": "0.1.0",
        }
        assert validate_promo({"id": f"demo-{slug}", **result.datos, "meta": meta}) == [], slug


def test_output_is_deterministic(adapter):
    assert listar(adapter) == listar(adapter)
    assert parse(adapter, "madrid") == parse(adapter, "madrid")


def test_record_fields(adapter):
    result = parse(adapter, "madrid")
    datos = result.datos
    assert datos["nombre"] == "Plan Vive Madrid"
    assert datos["viviendas_total"] == 1616
    assert datos["operador"] == CONFIG["operador"]
    assert (datos["fuente_id"], datos["programa"]) == ("plan-vive-cam", "PLAN_VIVE")
    assert (datos["regimen"], datos["modalidad"]) == ("DESCONOCIDO", "alquiler")
    assert datos["enlaces"] == {"oficial": f"{PAGE}#madrid", "solicitud": None, "bases": []}
    assert result.procedencia["/viviendas_total"]["evidencia"] == "Nº viviendas: 1.616"
    assert result.procedencia["/ubicacion/direccion"]["evidencia"] == "Ubicación: Valdebebas y Los Ahijones"
    assert result.procedencia["/estado"]["evidencia"] == "En fase de: Entrega y construcción"
    assert result.procedencia["/tipologias"]["evidencia"] == "Nº habitaciones: 1, 2 o 3 dormitorios"


def test_blocks_with_different_markup(adapter):
    assert parse(adapter, "colmenar-viejo").datos["viviendas_total"] == 915  # PRTR note in its own row
    assert parse(adapter, "torrejon-de-la-calzada").datos["viviendas_total"] == 143  # note in the cell


def test_requisitos_come_from_the_faq(adapter):
    result = parse(adapter, "getafe")
    requisitos = dict(result.datos["requisitos"])
    otros = requisitos.pop("otros")
    assert requisitos.pop("no_titular_vivienda") is True
    assert requisitos.pop("no_exigidos") == []
    assert all(value is None for value in requisitos.values())  # includes empadronamiento
    assert otros[:3] == [
        "Mayoría de edad o ser menor emancipado.",
        "Nacionalidad española o residencia legal en España.",
        "Destinar la vivienda a tu domicilio permanente y habitual.",
    ]
    assert len(otros) == 4
    assert "prioridad" in otros[3] and not any(c.isdigit() for c in otros[3])
    evidence = result.procedencia["/requisitos/otros"]
    assert evidence["documento"] == f"{PAGE}#dudas-frecuentes"
    assert "años" not in evidence["evidencia"]
    assert result.procedencia["/requisitos/no_titular_vivienda"]["evidencia"] == "No tener otra vivienda en propiedad."


def test_missing_faq_leaves_requisitos_unknown(adapter):
    result = parse(adapter, "getafe", replace('id="dudas-frecuentes"', 'id="otra-cosa"'))
    assert result.datos["requisitos"] == requisitos_desconocidos()
    assert not any(pointer.startswith("/requisitos") for pointer in result.procedencia)


# -- values ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fase", "estado"),
    [
        ("Construcción", "proxima"),
        ("En construcción", "proxima"),
        ("Próximamente", "proxima"),
        ("Entrega", "desconocido"),
        ("Comercialización y construcción", "desconocido"),
    ],
)
def test_estado(adapter, fase, estado):
    html = before_news(table("Parla", ("Nº viviendas:", "10"), ("En fase de:", fase)))
    assert parse(adapter, "parla", html).datos["estado"] == estado


@pytest.mark.parametrize(
    ("habitaciones", "dormitorios"),
    [
        ("1 o 2 dormitorios", [1, 2]),
        ("3 dormitorios", [3]),
        ("1 a 3 dormitorios", []),
        ("Hasta 3 dormitorios", []),
        ("Estudios y 1 dormitorio", []),
    ],
)
def test_only_listed_dormitorios(adapter, habitaciones, dormitorios):
    html = before_news(table("Parla", ("Nº viviendas:", "10"), ("Nº habitaciones:", habitaciones)))
    assert [t["dormitorios"] for t in parse(adapter, "parla", html).datos["tipologias"]] == dormitorios


@pytest.mark.parametrize("raw", ["Más de 100", "1.6", "0", "100 y 50", "9.000"])
def test_doubtful_viviendas_is_null(adapter, raw):
    result = parse(adapter, "alcorcon", replace("<td>822</td>", f"<td>{raw}</td>"))
    assert result.datos["viviendas_total"] is None
    assert "/viviendas_total" not in result.procedencia


# -- unrecognised structure ------------------------------------------------------------------------


def test_unknown_municipality_fails_only_its_ficha(adapter):
    html = replace("<caption>Pinto</caption>", "<caption>Pinto Norte</caption>")
    fichas = listar(adapter, html)
    assert len(fichas) == 26
    with pytest.raises(ValueError, match="Pinto Norte"):
        adapter.parsear_ficha(fichas["pinto-norte"], FakeFetcher(""))
    assert adapter.parsear_ficha(fichas["getafe"], FakeFetcher("")).datos["viviendas_total"] == 864


@pytest.mark.parametrize(
    "html",
    [
        pytest.param("<html><body><main><p>Mantenimiento</p></main></body></html>", id="other-page"),
        pytest.param(replace('id="promociones"', 'id="x"'), id="no-heading"),
        pytest.param(before_news("<p>Parla Nº viviendas: 100</p>"), id="block-as-paragraph"),
        pytest.param(before_news("<p>Parla: próximamente</p>"), id="block-without-labels"),
        pytest.param(before_news(table("Parla", ("Viviendas", "100"))), id="table-without-known-labels"),
        pytest.param(before_news(table("", ("Nº viviendas:", "100"))), id="table-without-caption"),
        pytest.param(before_news(table("Pinto", ("Nº viviendas:", "100"))), id="municipality-twice"),
        pytest.param(
            before_news(table("Parla", ("Nº viviendas:", "1"), ("Nº viviendas:", "2"))), id="merged-blocks"
        ),
        pytest.param(replace("</main>", "<div>Parla Nº viviendas: 100</div></main>"), id="block-outside-region"),
        pytest.param(HTML.replace("Nº viviendas:", "Viviendas:"), id="label-renamed-everywhere"),
    ],
)
def test_unrecognised_structure_raises(adapter, html):
    with pytest.raises(ListingError):
        adapter.listar(FakeFetcher(html))


# -- change detection ------------------------------------------------------------------------------


def selected_text(adapter, html: str) -> str:
    return "\n".join(node.text() for node in LexborHTMLParser(html).css(adapter.selector_hash()))


def test_selector_covers_blocks_and_faq_but_not_news(adapter):
    text = selected_text(adapter, HTML)
    assert text.count("En fase de:") == 26
    assert "No tener otra vivienda en propiedad." in text
    assert "El nuevo reglamento" not in text
    assert "6.530" not in text
    assert selected_text(adapter, replace("El nuevo reglamento", "Otra noticia")) == text
    assert selected_text(adapter, replace("<td>822</td>", "<td>823</td>")) != text
    assert "Parla" in selected_text(adapter, before_news("<p>Parla</p>"))
