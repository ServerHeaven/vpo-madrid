"""EMVS Madrid: promotions "en proyecto y obra" plus the lottery page.

Two pages are listed: the works-in-progress index (every entry is ``proxima``) and the lottery
page, whose promotion takes its registration state and requirements from that page and its
physical data from its own ficha. All pages are SharePoint; content lives in the right column.
HTML comments (which hold a retired "Inscríbete" button) never reach selectors or text.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlsplit

from selectolax.lexbor import LexborHTMLParser, LexborNode

from ..core.normalize import fold, parse_number_es, slugify
from .base import (
    DocumentoRef,
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

LOTTERY_URL = "https://www.emvs.es/Vivienda/SorteoPromocion"

_CONTENT = "#CenterRightColumn"
_HOSTS = frozenset({"www.emvs.es", "emvs.es"})
_FICHA_PATH = re.compile(r"/proyectos/promociones/paginas/([a-z0-9_-]+)\.aspx", re.IGNORECASE)
_HIDDEN = '[hidden], .hidden, [style*="display:none"], [style*="display: none"]'

_DISTRICTS = {
    slugify(name): name
    for name in (
        "Centro", "Arganzuela", "Retiro", "Salamanca", "Chamartín", "Tetuán", "Chamberí",
        "Fuencarral-El Pardo", "Moncloa-Aravaca", "Latina", "Carabanchel", "Usera",
        "Puente de Vallecas", "Moratalaz", "Ciudad Lineal", "Hortaleza", "Villaverde",
        "Villa de Vallecas", "Vicálvaro", "San Blas-Canillejas", "Barajas",
    )
}  # fmt: skip
_STREET = re.compile(
    r"(?<!\w)(?:C/|Calle\b|Av\.|Avd\.|Avda\b|Avenida\b|Paseo\b|Plaza\b|Pza\.|Camino\b"
    r"|Carretera\b|Ronda\b|Glorieta\b|Travesía\b)"
)

# All the patterns below run on fold()ed text.
_LISTING_COUNT = re.compile(r"(\d+) ?viviendas?")
_H1_COUNT = re.compile(r"(\d+) viviendas?\.?")
_TABLE_COUNT = re.compile(r"(\d+) ?(?:/.*)?")
_LOTTERY_COUNT = re.compile(r"\b(\d+) viviendas en alquiler")
_REGIMEN = re.compile(r"(vppa|vppb|vppl|vpo)(?: ?\(calificacion (?:provisional|definitiva)[^)]*\))?")
_PROGRAMA = re.compile(r"((?:\dd(?: ?, ?| y ))*\dd) ?\(([^()]*)\)")
_RENTAL = re.compile(
    r"proteccion publica para arrendamiento|viviendas (?:publicas )?(?:de|en) alquiler asequible"
    r"|regimen de alquiler"
)
_SALE = re.compile(r"\ben venta\b|\bcompraventa\b|\bopcion (?:de|a) compra\b")

_CLOSED = re.compile(
    r"plazo de inscripcion (?:ya )?(?:ha finalizado|ha concluido|(?:esta |se encuentra )?(?:cerrado|finalizado))"
    r"(?: el(?: dia)? (?P<d>\d{1,2}) de (?P<m>[a-z]+) de (?P<y>20\d{2}))?"
)
_OPEN = re.compile(
    r"(?<!no )(?:plazo de inscripcion (?:esta|se encuentra) abierto|(?:esta|se encuentra) abierto el plazo de inscripcion)"
)
_BUTTON_TEXTS = frozenset({"inscribete"})
_MONTHS = {
    name: number
    for number, name in enumerate(
        "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), 1
    )
} | {"setiembre": 9}

_REQ_AGE = re.compile(r"tener entre (\d{2}) y (\d{2}) anos\.?")
_REQ_RESIDENCE = re.compile(
    r"ser espanol o residente legal en espana y estar empadronado en el municipio de madrid "
    r"con una antiguedad minima de (\d{1,2}) anos\.?"
)
_REQ_INCOME = re.compile(
    r"tener unos ingresos familiares de entre (\d+(?:,\d+)?) y (\d+(?:,\d+)?) veces el iprem "
    r"en el ejercicio fiscal (20\d{2})\.?"
)
_REQ_NO_OWNER = re.compile(
    r"no ser titular del pleno dominio o de un derecho de uso o disfrute sobre otra vivienda "
    r"en todo el territorio nacional\.?"
)
_NATIONALITY = "Ser español o residente legal en España"
_MORE_REQUIREMENTS = "Hay requisitos adicionales no recogidos aquí: consulta la página oficial."


class EmvsMadridAdapter(SourceAdapter):
    id = "emvs-madrid"

    # -- listing ---------------------------------------------------------------------------

    def listar(self, http: Fetcher) -> list[Ficha]:
        fichas = {ficha.url: ficha for ficha in self._works_listing(http.get(self.config["url"]))}
        lottery = self._lottery_ficha(http.get(LOTTERY_URL))
        listed = fichas.get(lottery.url)
        if listed is not None:  # also in the index: one promotion, lottery data wins
            lottery = Ficha(listed.url, listed.nombre, listed.extra | lottery.extra)
        fichas[lottery.url] = lottery
        return list(fichas.values())

    def _works_listing(self, response: Response) -> list[Ficha]:
        column = _column(response)
        if column is None or not _has_heading(column, "h1", "promociones en proyecto y obra"):
            raise ListingError("EMVS: la página de promociones en proyecto y obra ha cambiado")
        blocks = column.css("#MenuBloquesImg")
        items = blocks[0].css("li") if len(blocks) == 1 else []
        if not items:
            raise ListingError("EMVS: no se encuentra el bloque de promociones en proyecto y obra")

        fichas: list[Ficha] = []
        seen: set[str] = set()
        for item in items:
            links = item.css("a[href]")
            url = _ficha_url(links[0].attributes.get("href"), response.url) if len(links) == 1 else None
            spans = [child for child in links[0].iter() if child.tag == "span"] if url else []
            nombre = _clean(spans[0].text()) if spans else ""
            if url is None or len(nombre) < 2 or url in seen:
                raise ListingError(f"EMVS: entrada no reconocida en el listado: '{_clean(item.text())[:80]}'")
            seen.add(url)
            count = _LISTING_COUNT.fullmatch(fold(spans[1].text(separator=" "))) if len(spans) > 1 else None
            fichas.append(Ficha(url, nombre, {"viviendas_listado": int(count[1]) if count else None}))
        return fichas

    def _lottery_ficha(self, response: Response) -> Ficha:
        column = _column(response)
        if column is None or not any(fold(h.text()).startswith("sorteo ") for h in column.css("h1")):
            raise ListingError("EMVS: la página del sorteo ha cambiado")
        links: dict[str, str] = {}
        for link in column.css("a[href]"):
            url = _ficha_url(link.attributes.get("href"), response.url)
            if url:
                links[url] = links.get(url) or _clean(link.attributes.get("title") or "")
        if len(links) != 1:
            raise ListingError(f"EMVS: la página del sorteo enlaza {len(links)} fichas de promoción, se esperaba 1")
        ((url, nombre),) = links.items()
        if len(nombre) < 2:
            raise ListingError("EMVS: el enlace a la ficha del sorteo no indica el nombre de la promoción")
        return Ficha(url, nombre, {"sorteo": True})

    # -- ficha -----------------------------------------------------------------------------

    def parsear_ficha(self, ficha: Ficha, http: Fetcher) -> Parsed:
        response = http.get(ficha.url)
        column = _column(response)
        article = column.css_first("article#FichaPromocion") if column is not None else None
        heading = article.css_first("header h1") if article is not None else None
        if heading is None:
            raise ValueError(f"EMVS: la ficha no tiene el formato esperado: {ficha.url}")
        content = fold(article.text(separator=" "))
        if _SALE.search(content):
            raise ValueError(f"EMVS: la ficha menciona venta u opción de compra, revisar a mano: {ficha.url}")

        source = ficha.url
        procedencia: dict[str, dict[str, Any]] = {}

        def note(pointer: str, evidence: str, url: str = source) -> None:
            procedencia[pointer] = procedencia_html(url, evidence)

        table = _data_table(article)
        distrito, direccion, subtitle = _location(article)
        if distrito:
            note("/ubicacion/distrito", subtitle)
        if direccion:
            note("/ubicacion/direccion", subtitle)

        counts: list[tuple[int, str, str]] = []  # (value, evidence, url)
        span = heading.css_first("span")
        if span is not None and (m := _H1_COUNT.fullmatch(fold(span.text()))):
            counts.append((int(m[1]), _clean(heading.text()), source))
        label, value = _row(table, "viviendas /")
        if m := _TABLE_COUNT.fullmatch(fold(value)):
            counts.append((int(m[1]), f"{label}: {value}", source))
        if (listed := ficha.extra.get("viviendas_listado")) is not None:
            counts.append((listed, f"{ficha.nombre}: {listed} viviendas", self.config["url"]))

        regimen = "DESCONOCIDO"
        label, value = _row(table, "calificacion de vivienda protegida")
        if m := _REGIMEN.fullmatch(fold(value)):
            regimen = m[1].upper()
            note("/regimen", f"{label}: {value}")

        if m := _RENTAL.search(content):
            note("/modalidad", _sentence_with(article, m[0]))
        elif regimen == "VPPA":
            note("/modalidad", f"{label}: {value}")

        requisitos = requisitos_desconocidos()
        fechas = fechas_desconocidas()
        solicitud = None
        oficial = ficha.url
        if ficha.extra.get("sorteo"):
            oficial = LOTTERY_URL
            page = http.get(LOTTERY_URL)
            lottery = _column(page)
            if lottery is None:
                raise ValueError("EMVS: la página del sorteo no tiene el formato esperado")
            text = fold(lottery.text(separator=" "))
            if _SALE.search(text):
                raise ValueError("EMVS: la página del sorteo menciona venta u opción de compra, revisar a mano")
            if m := _RENTAL.search(text):
                note("/modalidad", _sentence_with(lottery, m[0]), LOTTERY_URL)
            if m := _LOTTERY_COUNT.search(text):
                counts.append((int(m[1]), _sentence_with(lottery, m[0]), LOTTERY_URL))
            estado, fin, solicitud, evidence = _registration(lottery, page.url)
            if evidence:
                note("/estado", evidence, LOTTERY_URL)
            if fin:
                fechas["inscripcion_fin"] = fin
                note("/fechas/inscripcion_fin", evidence, LOTTERY_URL)
            for key, (parsed, proof) in _requirements(lottery).items():
                requisitos[key] = parsed
                note(f"/requisitos/{key}", proof, LOTTERY_URL)
        else:
            estado = "proxima"
            note("/estado", f"Promociones en proyecto y obra: {ficha.nombre}", self.config["url"])

        viviendas = None
        if counts and len({count for count, _, _ in counts}) == 1 and 1 <= counts[0][0] <= 5000:
            viviendas = counts[0][0]
            note("/viviendas_total", counts[0][1], counts[0][2])

        label, value = _row(table, "programa de viviendas")
        tipologias = _tipologias(value, viviendas)
        if tipologias:
            note("/tipologias", f"{label}: {value}")

        datos = {
            "nombre": ficha.nombre,
            "operador": dict(self.config["operador"]),
            "fuente_id": self.id,
            "regimen": regimen,
            "programa": "EMVS_MADRID",
            "modalidad": "alquiler" if "/modalidad" in procedencia else None,
            "estado": estado,
            "ubicacion": {
                "municipio_ine": "28079",
                "municipio": "Madrid",
                "distrito": distrito,
                "direccion": direccion,
                "lat": None,
                "lon": None,
            },
            "viviendas_total": viviendas,
            "tipologias": tipologias,
            "requisitos": requisitos,
            "fechas": fechas,
            "enlaces": {"oficial": oficial, "solicitud": solicitud, "bases": []},
        }
        return Parsed(datos, procedencia)

    def documentos(self, ficha: Ficha, http: Fetcher) -> list[DocumentoRef]:
        response = http.get(LOTTERY_URL if ficha.extra.get("sorteo") else ficha.url)
        column = _column(response)
        found: dict[str, str] = {}
        for link in column.css("a[href]") if column is not None else []:
            href = (link.attributes.get("href") or "").strip()
            url = quote(urljoin(response.url, href), safe=":/?&=#%()")
            title = _clean(link.attributes.get("title") or "") or _clean(link.text())
            if not urlsplit(url).path.lower().endswith(".pdf"):
                continue
            if "bases" in fold(f"{title} {link.text()} {unquote(href)}"):
                found.setdefault(url, title or "Bases")
        return [DocumentoRef(url, title, len(found) == 1) for url, title in found.items()]

    def selector_hash(self) -> str:
        return _CONTENT


# -- page helpers ------------------------------------------------------------------------------


def _clean(text: str) -> str:
    return " ".join(text.replace("\u200b", "").replace("\ufeff", "").split())


def _column(response: Response) -> LexborNode | None:
    """The content column without scripts, styles and hidden elements."""
    tree = LexborHTMLParser(response.text)
    tree.strip_tags(["script", "style", "noscript", "template"])
    column = tree.css_first(_CONTENT)
    if column is not None:
        for node in column.css(_HIDDEN):
            node.decompose()
    return column


def _has_heading(node: LexborNode, tag: str, folded: str) -> bool:
    return any(fold(h.text()) == folded for h in node.css(tag))


def _ficha_url(href: str | None, base: str) -> str | None:
    """Canonical ficha URL (SharePoint paths are case-insensitive), or None for other links."""
    parts = urlsplit(urljoin(base, (href or "").strip()))
    match = _FICHA_PATH.fullmatch(parts.path)
    if parts.scheme not in ("http", "https") or (parts.hostname or "") not in _HOSTS or not match:
        return None
    return f"https://www.emvs.es/Proyectos/Promociones/Paginas/{match[1].upper()}.aspx"


def _sentence_with(node: LexborNode, folded_phrase: str) -> str:
    """Literal text of the first sentence containing a phrase found on fold()ed text."""
    for block in node.css("p, li, h2, h3, h4"):
        for sentence in re.split(r"(?<=\.)\s+", _clean(block.text())):
            if folded_phrase in fold(sentence):
                return sentence
    return folded_phrase


def _data_table(article: LexborNode) -> list[tuple[str, str]]:
    """(label, value) pairs of the ficha's side column."""
    rows = []
    for paragraph in article.css("li p"):
        strong = paragraph.css_first("strong")
        if strong is None:
            continue
        value = _clean(strong.text(separator=" "))
        full = _clean(paragraph.text(separator=" "))
        cut = full.find(value) if value else -1
        rows.append((full[:cut].strip() if cut >= 0 else full, value))
    return rows


def _row(table: list[tuple[str, str]], prefix: str) -> tuple[str, str]:
    """The only row whose label starts with ``prefix``; empty strings if none or several."""
    matches = [row for row in table if fold(row[0]).startswith(prefix)]
    return matches[0] if len(matches) == 1 else ("", "")


def _location(article: LexborNode) -> tuple[str | None, str | None, str]:
    """(district, address, literal subtitle) from 'Barajas. C/ Venus, 5-7'."""
    node = article.css_first("header .subtitle")
    subtitle = _clean(node.text(separator=" ")) if node is not None else ""
    street = _STREET.search(subtitle)
    area = subtitle[: street.start()] if street else subtitle
    # An area that is not one of the 21 districts (e.g. "Ensanche de Vallecas") stays unknown.
    distrito = _DISTRICTS.get(slugify(area))
    direccion = subtitle[street.start() :].rstrip(" .") if street else None
    return distrito, direccion or None, subtitle


def _tipologias(value: str, total: int | None) -> list[dict[str, Any]]:
    """'2D, 3D y 4D (12 + 2 PMR / 20 / 2)'. Unit counts are kept only if they add up to the total."""
    match = _PROGRAMA.match(fold(value))
    if not match:
        return []
    rooms = [int(n) for n in re.findall(r"(\d)d", match[1])]
    if len(set(rooms)) != len(rooms) or any(n > 6 for n in rooms):
        return []

    if "/" in match[2]:
        groups, shape = match[2].split("/"), r" *(\d+)(?: *\+ *(\d+) *pmr)? *"
    else:
        groups, shape = match[2].split("+"), r" *(\d+)() *"
    parsed = [re.fullmatch(shape, group) for group in groups]
    units: list[int] | None = None
    if len(parsed) == len(rooms) and all(parsed):
        units = [int(m[1]) + int(m[2] or 0) for m in parsed]
        if sum(units) != total:
            units = None

    result = []
    for index, dormitorios in enumerate(rooms):
        if units is not None and units[index] == 0:
            continue  # "1D, 2D ... (0+14+...)": there are no such homes
        entry = tipologia(dormitorios)
        entry["num_viviendas"] = units[index] if units is not None else None
        result.append(entry)
    return result


# -- lottery page ------------------------------------------------------------------------------


def _registration(column: LexborNode, base: str) -> tuple[str, str | None, str | None, str | None]:
    """(estado, inscripcion_fin, solicitud, evidence) from what is visible on the page."""
    folded = fold(column.text(separator=" "))
    closed = list(_CLOSED.finditer(folded))
    opened = _OPEN.search(folded)
    button = next((a for a in column.css("a[href]") if fold(a.text()).strip(" !.") in _BUTTON_TEXTS), None)

    if closed and not (opened or button):
        dates = {_date(m["d"], m["m"], m["y"]) for m in closed if m["d"]}
        fin = dates.pop() if len(dates) == 1 else None
        longest = max(closed, key=lambda m: len(m[0]))
        return "inscripcion_cerrada", fin, None, _sentence_with(column, longest[0])
    if (opened or button) and not closed:
        href = urljoin(base, button.attributes["href"].strip()) if button else ""
        solicitud = href if href.startswith(("https://", "http://")) else None
        evidence = _sentence_with(column, opened[0]) if opened else f"Botón visible: {_clean(button.text())}"
        return "inscripcion_abierta", None, solicitud, evidence
    return "desconocido", None, None, None


def _date(day: str, month: str, year: str) -> str | None:
    try:
        return date(int(year), _MONTHS[month], int(day)).isoformat()
    except (KeyError, ValueError):
        return None


def _requirement_items(column: LexborNode) -> list[str]:
    for heading in column.css("h2"):
        if fold(heading.text()) == "los requisitos que tienes que cumplir":
            lists = [
                ul for ul in heading.parent.css("ul") if "docLista" not in (ul.attributes.get("class") or "")
            ]
            if len(lists) == 1:
                return [text for li in lists[0].css("li") if (text := _clean(li.text()))]
    raise ValueError("EMVS: no se encuentra la lista de requisitos en la página del sorteo")


def _requirements(column: LexborNode) -> dict[str, tuple[Any, str]]:
    """Requisitos key -> (value, evidence). Only keys with a single, plausible value."""
    candidates: dict[str, list[tuple[Any, str]]] = {}
    otros: list[str] = []
    evidence_otros: list[str] = []

    def add(key: str, value: Any, proof: str) -> None:
        candidates.setdefault(key, []).append((value, proof))

    def extra(text: str, proof: str) -> None:
        if text not in otros:
            otros.append(text)
            evidence_otros.append(proof)

    for item in _requirement_items(column):
        text = fold(item)
        if (m := _REQ_AGE.fullmatch(text)) and 16 <= int(m[1]) < int(m[2]) <= 99:
            add("edad", {"min": int(m[1]), "max": int(m[2]), "tipo": "requisito"}, item)
        elif (m := _REQ_RESIDENCE.fullmatch(text)) and int(m[1]) <= 20:
            residence = {
                "ambito": "municipio",
                "municipio_ine": "28079",
                "anios_min": int(m[1]),
                "ininterrumpido": None,
                "alternativa_trabajo": None,
            }
            add("empadronamiento", residence, item)
            extra(_NATIONALITY, item)
        elif m := _REQ_INCOME.fullmatch(text):
            low, high = parse_number_es(m[1]), parse_number_es(m[2])
            if low is not None and high is not None and 0 <= low < high <= 15:
                add("ingresos_min_iprem", low, item)
                add("ingresos_max_iprem", high, item)
                add("iprem_ejercicio", int(m[3]), item)
            else:
                extra(item if len(item) <= 300 else _MORE_REQUIREMENTS, item)
        elif _REQ_NO_OWNER.fullmatch(text):
            add("no_titular_vivienda", True, item)
        else:  # not expressible in the schema, or worded in a way we do not parse
            extra(item if len(item) <= 300 else _MORE_REQUIREMENTS, item)

    result: dict[str, tuple[Any, str]] = {}
    for key, found in candidates.items():
        if all(value == found[0][0] for value, _ in found):
            result[key] = found[0]
        else:  # contradiction: the field stays null, the statements stay readable
            for _, proof in found:
                extra(proof if len(proof) <= 300 else _MORE_REQUIREMENTS, proof)
    if otros:
        result["otros"] = (otros, " | ".join(evidence_otros))
    return result
