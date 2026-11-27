"""EMVIALSA (Empresa Municipal de la Vivienda de Alcobendas): rental promotions.

The promotions page has one tab per category. Listed here: the rental entries of "En Obra", plus
any rental entry of "En Alquiler y Cesión de Uso" that has a registration call not marked as
closed on the registration page. Delivered stock without a live call is left out, as are
"alojamientos dotacionales" (a temporary assignment of use, not a rental home).

Each tab and the list of calls are paginated by script after ``limit`` entries. Only the first
page is in the HTML, so a full page raises ListingError instead of returning a partial list.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlsplit

from selectolax.lexbor import LexborHTMLParser, LexborNode

from ..core.normalize import fold
from .base import (
    Fetcher,
    Ficha,
    ListingError,
    Parsed,
    Response,
    SourceAdapter,
    fechas_desconocidas,
    procedencia_html,
    requisitos_desconocidos,
    tipologia,
)

CALLS_URL = "https://emvialsa.org/acceso-a-la-vivienda/inscripciones"

_CONTENT = "#sp-component"
_HOSTS = frozenset({"emvialsa.org", "www.emvialsa.org"})
_FICHA_PATH = re.compile(r"/promocion/(?:en-obra|en-alquiler-y-cesion-de-uso)/[a-z0-9-]+")
_CALL_PATH = re.compile(r"/convocatoria-inscripcion/[a-z0-9-]+")
_WORKS_TAB = "en obra"
_RENTAL_TAB = "en alquiler y cesion de uso"
_CALLS_TAB = "convocatorias"

# All the patterns below run on fold()ed text.
_RENTAL = re.compile(r"\b(?:alquiler|arrendamiento)\b")
_SALE = re.compile(r"\b(?:venta|compraventa)\b")
_SALE_IN_FICHA = re.compile(r"\ben venta\b|\bcompraventa\b")
_BUY_OPTION = re.compile(r"\bopcion (?:de|a) compra\b")
_SHARED_USE = re.compile(r"\balojamientos? dotacional(?:es)?\b")
_PLANNING = re.compile(r"en planificacion\.?")
_CLOSED = re.compile(r"plazo (?:de )?inscripcion cerrado\.?")
_OPEN = re.compile(r"plazo (?:de )?inscripcion abierto\.?")
_REGIMEN = re.compile(r"\b(vppa|vppb|vppl|vpo)\b")
_COUNT = re.compile(r"(\d+) (?:vppa|vppb|vppl|vpo|viviendas)\b")
_UNITS = re.compile(r"(\d+) ?/ ?\d+ ?/ ?\d+(?: ?/ ?\d+)?")
_PROGRAMA = re.compile(r"(?:\dd(?: ?, ?| y ))*\dd")
_PER_TYPE = re.compile(r"\b(\d+) (?:son de|viviendas? (?:adaptadas )?de) (\d|un|dos|tres|cuatro) dormitorios?")
_WORDS = {"un": 1, "dos": 2, "tres": 3, "cuatro": 4}
_STREET_NUMBER = re.compile(r".+, \d+(?: ?- ?\d+)?")


class EmvAlcobendasAdapter(SourceAdapter):
    id = "emvialsa-alcobendas"

    # -- listing ---------------------------------------------------------------------------

    def listar(self, http: Fetcher) -> list[Ficha]:
        page = http.get(self.config["url"])
        content = _content(page)
        if content is None or not any(fold(h.text()) == "promociones de vivienda" for h in content.css("h1")):
            raise ListingError("EMVIALSA: la página de promociones ha cambiado")

        works = _entries(_pane(content, _WORKS_TAB), page.url, _FICHA_PATH, complete=True)
        delivered_rentals = _entries(_pane(content, _RENTAL_TAB), page.url, _FICHA_PATH, complete=False)

        rentals: dict[str, dict[str, Any]] = {}  # url -> entry
        for entry in works:
            text = fold(entry["resumen"])
            if _RENTAL.search(text):
                if _SALE.search(text):
                    raise ListingError(f"EMVIALSA: promoción de venta y alquiler a la vez: '{entry['nombre']}'")
                rentals[entry["url"]] = entry | {"en_obra": True}
            elif not (_SHARED_USE.search(text) or _PLANNING.fullmatch(text) or _SALE.search(text)):
                raise ListingError(f"EMVIALSA: tipo de promoción no reconocido: '{entry['resumen'][:80]}'")

        candidates = dict(rentals)
        for entry in delivered_rentals:
            if _RENTAL.search(fold(entry["resumen"])):
                candidates.setdefault(entry["url"], entry | {"en_obra": False})

        calls: dict[str, list[dict[str, str]]] = {}  # ficha url -> its registration calls
        for call in self._calls(http.get(CALLS_URL)):
            title = fold(call["nombre"])
            status = fold(call["resumen"])
            closed = bool(_CLOSED.fullmatch(status))
            matches = [url for url, entry in candidates.items() if _names(title, entry["nombre"])]
            if len(matches) == 1:
                calls.setdefault(matches[0], []).append(call)
            elif not closed and (_RENTAL.search(title) or not (_SALE.search(title) or _SHARED_USE.search(title))):
                raise ListingError(
                    f"EMVIALSA: convocatoria sin cerrar que no corresponde a una promoción: '{call['nombre'][:100]}'"
                )

        fichas: list[Ficha] = []
        for url, entry in candidates.items():
            own = calls.get(url, [])
            live = [call for call in own if not _CLOSED.fullmatch(fold(call["resumen"]))]
            if not (entry["en_obra"] or live):
                continue
            closed = [call for call in own if call not in live]
            fichas.append(
                Ficha(
                    url,
                    entry["nombre"],
                    {
                        "resumen": entry["resumen"],
                        "en_obra": entry["en_obra"],
                        "convocatorias_vivas": live,
                        "convocatorias_cerradas": closed,
                    },
                )
            )
        return fichas

    def _calls(self, response: Response) -> list[dict[str, str]]:
        content = _content(response)
        if content is None:
            raise ListingError("EMVIALSA: la página de inscripciones ha cambiado")
        return _entries(_pane(content, _CALLS_TAB), response.url, _CALL_PATH, complete=True)

    # -- ficha -----------------------------------------------------------------------------

    def parsear_ficha(self, ficha: Ficha, http: Fetcher) -> Parsed:
        content = _content(http.get(ficha.url))
        title = content.css_first("h1") if content is not None else None
        subtitle = content.css_first("h3.sppb-addon-title") if content is not None else None
        if title is None or subtitle is None or not _names(fold(title.text()), ficha.nombre):
            raise ValueError(f"EMVIALSA: la ficha no tiene el formato esperado: {ficha.url}")
        resumen = ficha.extra["resumen"]
        heading = _clean(subtitle.text())
        paragraphs = [text for p in content.css("p, li") if (text := _clean(p.text()))]
        everything = fold(" ".join(paragraphs))
        if _SALE_IN_FICHA.search(everything):
            raise ValueError(f"EMVIALSA: la ficha menciona una venta, revisar a mano: {ficha.url}")

        listing = self.config["url"]
        procedencia: dict[str, dict[str, Any]] = {}

        def note(pointer: str, evidence: str, url: str = ficha.url) -> None:
            procedencia[pointer] = procedencia_html(url, evidence)

        listed = f"{ficha.nombre}: {resumen}"
        modalidad = "alquiler_opcion_compra" if _BUY_OPTION.search(fold(f"{resumen} {heading}")) else "alquiler"
        if modalidad == "alquiler" and _BUY_OPTION.search(everything):
            raise ValueError(f"EMVIALSA: la ficha menciona opción de compra, revisar a mano: {ficha.url}")
        note("/modalidad", listed, listing)

        codes = set(_REGIMEN.findall(fold(f"{resumen} {heading}")))
        regimen = "DESCONOCIDO"
        if len(codes) == 1:  # two different codes between listing and ficha: unknown
            code = codes.pop()
            regimen = code.upper()
            if _REGIMEN.search(fold(resumen)):
                note("/regimen", listed, listing)
            else:
                note("/regimen", heading)

        features = _features(content)
        counts: list[tuple[int, str, str]] = []  # (value, evidence, url)
        if m := _COUNT.match(fold(resumen)):
            counts.append((int(m[1]), listed, listing))
        if m := _COUNT.match(fold(heading)):
            counts.append((int(m[1]), heading, ficha.url))
        label, value = _feature(features, "viviendas /")
        if m := _UNITS.fullmatch(fold(value)):
            counts.append((int(m[1]), f"{label}: {value}", ficha.url))
        viviendas = None
        if counts and len({count for count, _, _ in counts}) == 1 and 1 <= counts[0][0] <= 5000:
            viviendas, evidence, url = counts[0]
            note("/viviendas_total", evidence, url)

        label, value = _feature(features, "programa de viviendas")
        tipologias = _tipologias(value, viviendas, paragraphs)
        if tipologias:
            note("/tipologias", f"{label}: {value}")

        estado, solicitud = "proxima", None
        live = ficha.extra["convocatorias_vivas"]
        closed = ficha.extra["convocatorias_cerradas"]
        if live:
            call = live[0]
            estado = "desconocido"
            if len(live) == 1 and _OPEN.fullmatch(fold(call["resumen"])):
                estado, solicitud = "inscripcion_abierta", call["url"]
            note("/estado", f"{call['nombre']}: {call['resumen']}", CALLS_URL)
        elif closed:
            estado = "inscripcion_cerrada"
            note("/estado", f"{closed[-1]['nombre']}: {closed[-1]['resumen']}", CALLS_URL)
        else:
            note("/estado", f"En Obra: {ficha.nombre}", listing)

        direccion = ficha.nombre if _STREET_NUMBER.fullmatch(ficha.nombre) else None
        if direccion:
            note("/ubicacion/direccion", _clean(title.text()))

        resolved = self.municipios.resolve("Alcobendas")
        if resolved is None:
            raise ValueError("EMVIALSA: municipio no reconocido: Alcobendas")
        datos = {
            "nombre": ficha.nombre,
            "operador": dict(self.config["operador"]),
            "fuente_id": self.id,
            "regimen": regimen,
            "programa": "EMV_MUNICIPAL",
            "modalidad": modalidad,
            "estado": estado,
            "ubicacion": {
                "municipio_ine": resolved[0],
                "municipio": resolved[1],
                "distrito": None,
                "direccion": direccion,
                "lat": None,
                "lon": None,
            },
            "viviendas_total": viviendas,
            "tipologias": tipologias,
            "requisitos": requisitos_desconocidos(),  # the registry's rules are not a promotion's rules
            "fechas": fechas_desconocidas(),
            "enlaces": {"oficial": ficha.url, "solicitud": solicitud, "bases": []},
        }
        return Parsed(datos, procedencia)

    def selector_hash(self) -> str:
        return _CONTENT


# -- page helpers ------------------------------------------------------------------------------


def _clean(text: str) -> str:
    return " ".join(text.replace("​", "").replace("﻿", "").split())


def _content(response: Response) -> LexborNode | None:
    html = re.sub(r"(?i)<br\b[^>]*>", " ", response.text)
    tree = LexborHTMLParser(html)
    tree.strip_tags(["script", "style", "noscript", "template"])
    return tree.css_first(_CONTENT)


def _pane(content: LexborNode, tab: str) -> LexborNode:
    """The panel of the only tab with this title."""
    links = [a for a in content.css("ul.sppb-nav a[aria-controls]") if fold(a.text()) == tab]
    if len(links) == 1:
        wanted = links[0].attributes.get("aria-controls")
        panes = [node for node in content.css("div.sppb-tab-pane") if node.attributes.get("id") == wanted]
        if len(panes) == 1:
            return panes[0]
    raise ListingError(f"EMVIALSA: no se encuentra la pestaña '{tab}'")


def _entries(pane: LexborNode, base: str, path: re.Pattern[str], *, complete: bool) -> list[dict[str, str]]:
    """Name, summary and URL of every entry of a panel. ``complete`` refuses a full page."""
    entries: list[dict[str, str]] = []
    items = pane.css("div.sppb-addon-article")
    for item in items:
        link = item.css_first("h4 a[href]")
        intro = item.css_first(".sppb-article-introtext")
        parts = urlsplit(urljoin(base, (link.attributes.get("href") or "").strip())) if link else None
        nombre = _clean(link.text()) if link else ""
        resumen = _clean(intro.text()) if intro else ""
        if parts is None or parts.hostname not in _HOSTS or not path.fullmatch(parts.path) or len(nombre) < 2:
            raise ListingError(f"EMVIALSA: entrada no reconocida: '{_clean(item.text())[:80]}'")
        entries.append({"nombre": nombre, "resumen": resumen, "url": f"https://emvialsa.org{parts.path}"})
    if not entries or len({entry["url"] for entry in entries}) != len(entries):
        raise ListingError("EMVIALSA: una pestaña está vacía o repite entradas")
    if complete:
        _check_not_truncated(pane, len(items))
    return entries


def _check_not_truncated(pane: LexborNode, found: int) -> None:
    settings = pane.css('input[name="sppb-articles-addon-settings"]')
    limits = [re.search(r'"limit"\s*:\s*"?(\d+)', node.attributes.get("value") or "") for node in settings]
    if len(limits) != 1 or limits[0] is None:
        raise ListingError("EMVIALSA: no se puede saber cuántas entradas admite la página")
    if found >= int(limits[0][1]):
        raise ListingError(f"EMVIALSA: la pestaña muestra {found} entradas, el máximo: puede haber más sin cargar")


def _names(folded_text: str, nombre: str) -> bool:
    """True if the text names this address ("velarde, 19" but not "velarde, 190")."""
    return re.search(rf"(?<![a-z0-9]){re.escape(fold(nombre))}(?![a-z0-9])", folded_text) is not None


def _features(content: LexborNode) -> list[tuple[str, str]]:
    """(label, value) pairs of the ficha's side column."""
    rows = []
    for box in content.css(".sppb-media-content"):
        label = box.css_first(".sppb-feature-box-title")
        value = box.css_first(".sppb-addon-text")
        if label is not None and value is not None:
            rows.append((_clean(label.text()), _clean(value.text(separator=" "))))
    return rows


def _feature(rows: list[tuple[str, str]], prefix: str) -> tuple[str, str]:
    """The only row whose label starts with ``prefix``; empty strings if none or several."""
    matches = [row for row in rows if fold(row[0]).startswith(prefix)]
    return matches[0] if len(matches) == 1 else ("", "")


def _tipologias(programa: str, total: int | None, paragraphs: list[str]) -> list[dict[str, Any]]:
    """Types from "1D, 2D y 3D". Unit counts only from one sentence that adds up to the total."""
    folded = fold(programa).rstrip(".")
    if not _PROGRAMA.fullmatch(folded):
        return []
    rooms = [int(n) for n in re.findall(r"(\d)d", folded)]
    if len(set(rooms)) != len(rooms) or any(n > 6 for n in rooms):
        return []

    units: dict[int, int] = {}
    sentences = [
        sentence
        for text in paragraphs
        for sentence in re.split(r"(?<=\.)\s+", fold(text))
        if total is not None and "abarca" in sentence and re.search(rf"\b{total} viviendas\b", sentence)
    ]
    if len(sentences) == 1:
        for count, word in _PER_TYPE.findall(sentences[0]):
            dormitorios = _WORDS.get(word) or int(word)
            units[dormitorios] = units.get(dormitorios, 0) + int(count)
        if set(units) != set(rooms) or sum(units.values()) != total or 0 in units.values():
            units = {}

    result = []
    for dormitorios in rooms:
        entry = tipologia(dormitorios)
        entry["num_viviendas"] = units.get(dormitorios)
        result.append(entry)
    return result
