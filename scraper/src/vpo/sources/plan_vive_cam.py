"""Plan Vive (Comunidad de Madrid): one aggregated record per municipality block.

The page has no per-promotion pages. After the "Promociones" heading there is one table per
municipality (caption = municipality, one row per datum); the general conditions are in the FAQ
accordion. Everything is read in ``listar`` and travels in ``Ficha.extra``.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

from selectolax.lexbor import LexborHTMLParser, LexborNode

from ..core.normalize import fold, parse_int_es, slugify
from .base import (
    Fetcher,
    Ficha,
    ListingError,
    Parsed,
    SourceAdapter,
    fechas_desconocidas,
    procedencia_html,
    requisitos_desconocidos,
    tipologia,
)

_SECTION = "section.paragraph--type--section"
_FAQ_SELECTOR = f"{_SECTION}:has(h2#dudas-frecuentes)"
_HEADING_WRAPPER = f"div:has(> {_SECTION} h2#promociones)"
# The heading's wrapper and every following sibling except the news, so that a block added in a
# new section or with a new layout is still inside the region.
_REGION_SELECTOR = f"{_HEADING_WRAPPER}, {_HEADING_WRAPPER} ~ div:not(:has(h2#contenidos-relacionados))"

# Row label (see _label_key) -> key in Ficha.extra
_LABELS = {
    "no viviendas": "viviendas",
    "en fase de": "fase",
    "no habitaciones": "habitaciones",
    "ubicacion": "ubicacion",
    "inscripciones": "inscripciones",
}
# Labels that only a promotion block uses: every occurrence in the page must be inside a block.
_BLOCK_MARKERS = ("no viviendas:", "en fase de:", "no habitaciones:")

_UPCOMING_PHASES = frozenset({"construccion", "en construccion", "proximamente"})
_VIVIENDAS = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+)(?:\s*\([^()]*\))?")
_DORMITORIOS = re.compile(r"\d(?:\s*(?:,|o|y)\s*\d)*\s+dormitorios?")
_NO_TITULAR = re.compile(r"no (?:tener|ser titular de|ser propietario de|poseer) (?:otra|ninguna) vivienda\b")
_PRIORITY = re.compile(r"(?<!no )\bse da prioridad\b")
_PRIORITY_YEARS = re.compile(r",?\s+con\s+(?:una\s+)?antig|\s*\d")
_PRIORITY_LINE = (
    "Preferencia, no requisito: tienen prioridad las personas empadronadas o con centro de trabajo "
    "en el municipio de la vivienda."
)
_MAX_OTRO = 300


def _parse_page(html: str) -> LexborHTMLParser:
    # Line breaks and block ends carry no text of their own: without this, words get glued.
    html = re.sub(r"(?i)<br\b[^>]*>", " ", html)
    html = re.sub(r"(?i)(</(?:p|li|div|td|th|tr|caption|h[1-6])>)", r" \1", html)
    return LexborHTMLParser(html)


def _clean(text: str) -> str:
    return " ".join(text.replace("​", "").split())


def _marker_text(node: LexborNode) -> str:
    return fold(node.text()).replace(".", "").replace("°", "o").replace(" :", ":")


def _label_key(label: str) -> str | None:
    return _LABELS.get(fold(label).replace(".", "").replace("°", "o").rstrip(": "))


def _absolute_url(base: str, href: str) -> str:
    return quote(urljoin(base, href.strip()), safe=":/?#[]@!$&'()*+,;=%-._~")


def _read_block(table: LexborNode, page_url: str) -> dict[str, Any]:
    caption = table.css_first("caption")
    name = _clean(caption.text()) if caption else ""
    if not slugify(name):
        raise ListingError("Plan Vive: hay una tabla de promociones sin nombre de municipio")
    block: dict[str, Any] = {"municipio": name, "inscripciones": []} | dict.fromkeys(
        ("viviendas", "fase", "habitaciones", "ubicacion")
    )
    seen: set[str] = set()
    for row in table.css("tr"):
        cells = [cell for cell in row.iter() if cell.tag in ("td", "th")]
        if not cells:
            continue
        if len(cells) > 1:
            label = _clean(cells[0].text())
            value = _clean(" ".join(cell.text() for cell in cells[1:]))
        else:
            head, colon, tail = _clean(cells[0].text()).partition(":")
            label, value = head + colon, tail.strip()
        key = _label_key(label)
        if key is None:
            continue
        if key in seen:  # two municipalities merged into one table would silently lose one
            raise ListingError(f"Plan Vive: la tabla de '{name}' repite el dato '{label}'")
        seen.add(key)
        if key == "inscripciones":
            hrefs = [a.attributes.get("href") for cell in cells for a in cell.css("a")]
            block[key] = list(dict.fromkeys(_absolute_url(page_url, href) for href in hrefs if href))
        elif value:
            block[key] = {"etiqueta": label, "valor": value}
    if not seen:
        raise ListingError(f"Plan Vive: la tabla '{name}' no tiene ningún dato reconocible")
    return block


def _read_blocks(tree: LexborHTMLParser, page_url: str) -> list[dict[str, Any]]:
    """All municipality blocks. Destructive: consumes the tables of ``tree``."""
    main = tree.css_first("main") or tree.body
    if main is None or tree.css_first("h2#promociones") is None:
        raise ListingError("Plan Vive: no se encuentra el apartado 'Promociones'")
    region = tree.css(_REGION_SELECTOR)
    tables = [table for node in region for table in node.css("table")]
    if not tables:
        raise ListingError("Plan Vive: no hay ninguna tabla de promociones")

    for marker in _BLOCK_MARKERS:
        in_page = _marker_text(main).count(marker)
        in_tables = sum(_marker_text(table).count(marker) for table in tables)
        if in_page != in_tables:
            raise ListingError(f"Plan Vive: '{marker}' aparece {in_page} veces y solo {in_tables} en las tablas")

    blocks = [_read_block(table, page_url) for table in tables]
    if not any(block["viviendas"] for block in blocks):
        raise ListingError("Plan Vive: ninguna tabla indica el número de viviendas")

    # Whatever is left in the region once the known parts are gone is a block we cannot read.
    for table in tables:
        table.decompose()
    for node in region:
        for known in node.css("h2#promociones, script, style, noscript, svg"):
            known.decompose()
        leftover = _clean(node.text())
        if leftover:
            raise ListingError(f"Plan Vive: texto no reconocido entre las promociones: '{leftover[:120]}'")
    return blocks


def _read_faq(tree: LexborHTMLParser) -> dict[str, Any]:
    requisitos: list[str] = []
    prioridad: str | None = None
    section = tree.css_first(_FAQ_SELECTOR)
    for item in section.css(".component-accordion-item") if section else []:
        question = item.css_first(".accordion-title")
        answer = item.css_first(".accordion-content")
        if question is None or answer is None:
            continue
        if "requisitos" in fold(question.text()):
            requisitos += [text for li in answer.css("li") if (text := _clean(li.text()))]
        for sentence in re.split(r"(?<=\.)\s+", _clean(answer.text())):
            folded = fold(sentence)
            if prioridad is None and _PRIORITY.search(folded) and "empadronad" in folded and "trabajo" in folded:
                # Evidence stops before the number of years: official sources disagree on it.
                prioridad = _PRIORITY_YEARS.split(sentence)[0]
    return {"requisitos": requisitos, "prioridad": prioridad}


def _viviendas(text: str) -> int | None:
    match = _VIVIENDAS.fullmatch(text)
    number = parse_int_es(match.group(1)) if match else None
    return number if number is not None and 1 <= number <= 5000 else None


def _dormitorios(text: str) -> list[int]:
    """Only counts listed one by one ("1, 2 o 3 dormitorios"); ranges and the rest are unknown."""
    folded = fold(text).rstrip(".")
    if not _DORMITORIOS.fullmatch(folded):
        return []
    counts = sorted({int(digit) for digit in re.findall(r"\d", folded)})
    return counts if counts[-1] <= 6 else []


class PlanViveCamAdapter(SourceAdapter):
    id = "plan-vive-cam"

    def listar(self, http: Fetcher) -> list[Ficha]:
        page_url = self.config["url"]
        tree = _parse_page(http.get(page_url).text)
        faq = _read_faq(tree)
        fichas: dict[str, Ficha] = {}
        for block in _read_blocks(tree, page_url):
            resolved = self.municipios.resolve(block["municipio"])
            municipio = resolved[1] if resolved else block["municipio"]
            url = f"{page_url}#{slugify(municipio)}"
            if url in fichas:
                raise ListingError(f"Plan Vive: el municipio '{municipio}' aparece en dos bloques")
            fichas[url] = Ficha(url=url, nombre=f"Plan Vive {municipio}", extra=block | {"faq": faq})
        return list(fichas.values())

    def parsear_ficha(self, ficha: Ficha, http: Fetcher) -> Parsed:
        block = ficha.extra
        resolved = self.municipios.resolve(block["municipio"])
        if resolved is None:
            raise ValueError(f"Plan Vive: municipio no reconocido: '{block['municipio']}'")
        ine, municipio = resolved
        procedencia: dict[str, dict[str, Any]] = {}

        def cite(pointer: str, key: str) -> None:
            datum = block[key]
            procedencia[pointer] = procedencia_html(ficha.url, f"{datum['etiqueta']} {datum['valor']}")

        def value(key: str) -> str | None:
            return block[key]["valor"] if block[key] else None

        viviendas = _viviendas(value("viviendas") or "")
        if viviendas is not None:
            cite("/viviendas_total", "viviendas")

        direccion = value("ubicacion")
        if direccion is not None:
            cite("/ubicacion/direccion", "ubicacion")

        fase = value("fase")
        estado = "proxima" if fase and fold(fase).rstrip(".") in _UPCOMING_PHASES else "desconocido"
        if fase is not None:
            cite("/estado", "fase")

        tipologias = [tipologia(n) for n in _dormitorios(value("habitaciones") or "")]
        if tipologias:
            cite("/tipologias", "habitaciones")

        links = block["inscripciones"]
        solicitud = links[0] if len(links) == 1 and urlsplit(links[0]).scheme in ("http", "https") else None

        return Parsed(
            datos={
                "nombre": ficha.nombre,
                "operador": dict(self.config["operador"]),
                "fuente_id": self.id,
                "regimen": "DESCONOCIDO",
                "programa": "PLAN_VIVE",
                "modalidad": "alquiler",
                "estado": estado,
                "ubicacion": {
                    "municipio_ine": ine,
                    "municipio": municipio,
                    "distrito": None,
                    "direccion": direccion,
                    "lat": None,
                    "lon": None,
                },
                "viviendas_total": viviendas,
                "tipologias": tipologias,
                "requisitos": self._requisitos(block["faq"], procedencia),
                "fechas": fechas_desconocidas(),
                "enlaces": {"oficial": ficha.url, "solicitud": solicitud, "bases": []},
            },
            procedencia=procedencia,
        )

    def _requisitos(self, faq: dict[str, Any], procedencia: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """General conditions stated in the FAQ. Income, effort rate and registration stay unknown."""
        requisitos = requisitos_desconocidos()
        faq_url = f"{self.config['url']}#dudas-frecuentes"
        otros: list[str] = []
        evidence: list[str] = []
        for text in faq["requisitos"]:
            if _NO_TITULAR.match(fold(text)):
                requisitos["no_titular_vivienda"] = True
                procedencia["/requisitos/no_titular_vivienda"] = procedencia_html(faq_url, text)
            else:
                otros.append(text if len(text) <= _MAX_OTRO else text[: _MAX_OTRO - 1] + "…")
                evidence.append(text)
        if faq["prioridad"]:
            otros.append(_PRIORITY_LINE)
            evidence.append(faq["prioridad"])
        if otros:
            requisitos["otros"] = otros
            procedencia["/requisitos/otros"] = procedencia_html(faq_url, " ".join(evidence))
        return requisitos

    def selector_hash(self) -> str:
        return f"{_FAQ_SELECTOR}, {_REGION_SELECTOR}"
