import hashlib

import pytest

from vpo.core.hashing import (
    SelectorNotFound,
    html_fragment_text,
    normalize_text,
    sha256_bytes,
    sha256_fragment,
    sha256_text,
)

PAGE = """<html><head><title>T</title></head><body>
<nav>Menú que cambia</nav>
<main id="ficha">
  <h1>Promoción   sintética</h1>
  <!-- generado a las 10:00 -->
  <script>var token = "{token}";</script>
  <style>.a {{ color: red }}</style>
  <noscript>Activa JavaScript</noscript>
  <input type="hidden" name="__VIEWSTATE" value="{token}">
  <p>Renta: <strong>550&nbsp;€</strong></p>
  <a href="{href}">Bases</a>
</main>
<footer>{token}</footer>
</body></html>"""


def page(token: str = "abc", href: str = "/bases.pdf") -> str:
    return PAGE.format(token=token, href=href)


def test_sha256_bytes():
    assert sha256_bytes(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_normalize_text():
    assert normalize_text("  ﬁcha   de​ vi­vienda﻿\n\t²  ") == "ficha de vivienda 2"


def test_sha256_text_ignores_formatting():
    assert sha256_text("a  b\n") == sha256_text("a b") == sha256_bytes(b"a b")
    assert sha256_text("a b") != sha256_text("ab")


def test_fragment_text_keeps_only_relevant_content():
    assert html_fragment_text(page(), "#ficha") == "Promoción sintética Renta: 550 € </bases.pdf> Bases"


def test_fragment_hash_ignores_tokens_and_markup_noise():
    assert sha256_fragment(page("abc"), "#ficha") == sha256_fragment(page("zzz"), "#ficha")
    reindented = page().replace("\n", "\n\n      ").replace("<main", "<main data-x='1'")
    assert sha256_fragment(reindented, "#ficha") == sha256_fragment(page(), "#ficha")


def test_fragment_hash_detects_text_and_link_changes():
    base = sha256_fragment(page(), "#ficha")
    assert sha256_fragment(page(href="/bases-v2.pdf"), "#ficha") != base
    assert sha256_fragment(page().replace("550", "560"), "#ficha") != base


def test_document_order_without_duplicates():
    html = '<div class="b">uno <p class="a">dos</p></div><p class="a">tres</p><div class="b">cuatro</div>'
    for selector in (".a, .b", ".b, .a", ".b, .a, div, p"):
        assert html_fragment_text(html, selector) == "uno dos tres cuatro"


def test_matching_anchor_includes_its_href():
    assert html_fragment_text('<a class="d" href="/x">X</a>', "a.d") == "</x> X"


def test_per_request_link_noise_is_removed():
    html = '<div><a href="/p;jsessionid={0}?id=1">P</a><a href="/cdn-cgi/l/email-protection#{0}">m</a></div>'
    assert sha256_fragment(html.format("aa11"), "div") == sha256_fragment(html.format("bb22"), "div")
    assert "/p?id=1" in html_fragment_text(html.format("aa11"), "div")


@pytest.mark.parametrize(
    "noise",
    [
        "Consultado el 27/11/2026",
        "Página visitada el: 27-11-2026 a las 10:15:03.",
        "Fecha de consulta: 27/11/2026, 9:05 h",
    ],
)
def test_visit_date_noise_is_removed(noise):
    assert html_fragment_text(f"<div><p>Dato</p><span>{noise}</span></div>", "div") == "Dato"


@pytest.mark.parametrize(
    "content",
    [
        "El listado podrá ser consultado el 15/01/2027",
        "Piso piloto visitado el 15/01/2027 antes del sorteo",
        "Fecha de visita: 15/01/2027",
        "Fecha de sorteo: 15/01/2027",
    ],
)
def test_real_dates_are_kept(content):
    assert html_fragment_text(f"<div>{content}</div>", "div") == content


def test_selector_not_found():
    with pytest.raises(SelectorNotFound):
        html_fragment_text(page(), "#no-existe")
    with pytest.raises(SelectorNotFound):
        sha256_fragment("", "main")


def test_match_without_text_is_not_an_error():
    assert html_fragment_text('<div id="v"></div>', "#v") == ""


def test_deeply_nested_page():
    html = "<div id='r'>" + "<span>" * 400 + "fondo" + "</span>" * 400 + "</div>"
    assert html_fragment_text(html, "#r") == "fondo"
