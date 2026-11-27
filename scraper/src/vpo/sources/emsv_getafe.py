"""EMSV (Empresa Municipal del Suelo y la Vivienda de Getafe): rental promotions.

The promotions page has a block "Alquiler de viviendas" mixing promotions (/promocion/<slug>/)
with services (aid, intermediation of private homes), which are skipped by an explicit list.

A promotion page links PDFs with lists of applicants and winners. Only link titles are read, and
the only document ever returned is the one titled "Bases reguladoras".
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

from selectolax.lexbor import LexborHTMLParser, LexborNode

from ..core.normalize import fold
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
)

_HOSTS = frozenset({"emsvgetafe.org", "www.emsvgetafe.org"})
_FICHA_PATH = re.compile(r"/promocion/[a-z0-9-]+/")
# Entries of the rental block that are services, not promotions.
_SERVICES = frozenset(
    f"/promociones/{slug}/" for slug in ("ayudas-alquiler", "programas-alquiler", "vivienda-abierta", "viviendas-compartidas")
)
_LISTING_BLOCK = "section.hogares-lst"
_RENTAL_HEADING = "alquiler de viviendas"
_SECTIONS = ("section.inn-banner", "section.sorito-sec", "section.grupo-cont-sec", "section.faqs-sc-container")
_PRIVATE_PATH = "/no-index/"

# All the patterns below run on fold()ed text.
_SALE = re.compile(r"\ben venta\b|\bcompraventa\b|\bopcion (?:de|a) compra\b")
_RENTAL = re.compile(r"\b(?:alquiler|arrendamiento|arrendatarios?)\b")
_RESULT = re.compile(r"resultado (?:del )?sorteo(?: (?P<d>\d{1,2})/(?P<m>\d{1,2})/(?P<y>20\d{2}))?")
_LOTTERY_STEP = re.compile(r"\blistado (?:provisional|definitivo)\b|\bnumeros del sorteo\b")
_RESIDENCE = re.compile(
    r"requisito necesario estar empadronado (?P<continuous>de manera ininterrumpida )?en el municipio "
    r"al menos desde el \d{1,2} de [a-z]+ de 20\d{2}(?P<only>, no permitiendose otras opciones)?\.$"
)
# FAQ answers kept as text: conditions the schema cannot express.
_OTHER_CONDITIONS = tuple(
    re.compile(pattern)
    for pattern in (
        r"requisito necesario estar empadronado",
        r"requisito necesario ser mayor de edad",
        r"^para optar a una vivienda del grupo \d",
        r"al menos uno de los solicitantes cumpla el requisito de empadronamiento",
        r"^no se admitiran solicitudes",
        r"gastos ordinarios de comunidad",
    )
)
_MAX_OTRO = 300


class EmsvGetafeAdapter(SourceAdapter):
    id = "emsv-getafe"

    # -- listing ---------------------------------------------------------------------------

    def listar(self, http: Fetcher) -> list[Ficha]:
        response = http.get(self.config["url"])
        tree = _tree(response)
        blocks = [
            heading.parent
            for heading in tree.css(f"{_LISTING_BLOCK} h3")
            if fold(heading.text()) == _RENTAL_HEADING
        ]
        links = blocks[0].css("li a[href]") if len(blocks) == 1 else []
        if not links:
            raise ListingError("EMSV Getafe: no se encuentra el bloque 'Alquiler de viviendas'")

        fichas: dict[str, Ficha] = {}
        for link in links:
            parts = urlsplit(urljoin(response.url, (link.attributes.get("href") or "").strip()))
            nombre = _clean(link.text())
            if parts.hostname in _HOSTS and parts.path in _SERVICES:
                continue
            if parts.hostname not in _HOSTS or not _FICHA_PATH.fullmatch(parts.path) or len(nombre) < 2:
                raise ListingError(f"EMSV Getafe: entrada de alquiler no reconocida: '{nombre[:80]}'")
            url = f"https://emsvgetafe.org{parts.path}"
            if url in fichas:
                raise ListingError(f"EMSV Getafe: el listado repite '{nombre[:80]}'")
            fichas[url] = Ficha(url, nombre)
        return list(fichas.values())

    # -- ficha -----------------------------------------------------------------------------

    def parsear_ficha(self, ficha: Ficha, http: Fetcher) -> Parsed:
        tree = _promotion_page(http.get(ficha.url), ficha.url)
        text = fold(" ".join(node.text(separator=" ") for selector in _SECTIONS for node in tree.css(selector)))
        if _SALE.search(text):
            raise ValueError(f"EMSV Getafe: la ficha menciona venta u opción de compra, revisar a mano: {ficha.url}")
        if not _RENTAL.search(text):
            raise ValueError(f"EMSV Getafe: la ficha no dice que sea un alquiler: {ficha.url}")

        resolved = self.municipios.resolve("Getafe")
        if resolved is None:
            raise ValueError("EMSV Getafe: municipio no reconocido: Getafe")
        ine, municipio = resolved

        procedencia: dict[str, dict[str, Any]] = {}

        def note(pointer: str, evidence: str, url: str = ficha.url) -> None:
            procedencia[pointer] = procedencia_html(url, evidence)

        note("/modalidad", f"Alquiler de viviendas: {ficha.nombre}", self.config["url"])

        fechas = fechas_desconocidas()
        estado, evidence, sorteo = _state(tree)
        if evidence:
            note("/estado", evidence)
        if sorteo:
            fechas["sorteo"] = sorteo
            note("/fechas/sorteo", evidence)

        requisitos = requisitos_desconocidos()
        _requirements(tree, ine, requisitos, note)

        datos = {
            "nombre": ficha.nombre,
            "operador": dict(self.config["operador"]),
            "fuente_id": self.id,
            "regimen": "DESCONOCIDO",
            "programa": "EMV_MUNICIPAL",
            "modalidad": "alquiler",
            "estado": estado,
            "ubicacion": {
                "municipio_ine": ine,
                "municipio": municipio,
                "distrito": None,
                "direccion": None,
                "lat": None,
                "lon": None,
            },
            "viviendas_total": None,  # the page gives counts per lottery group, never a total
            "tipologias": [],
            "requisitos": requisitos,
            "fechas": fechas,
            "enlaces": {"oficial": ficha.url, "solicitud": None, "bases": []},
        }
        return Parsed(datos, procedencia)

    def documentos(self, ficha: Ficha, http: Fetcher) -> list[DocumentoRef]:
        response = http.get(ficha.url)
        tree = _promotion_page(response, ficha.url)
        found: dict[str, str] = {}
        for link in tree.css("section.sorito-sec a[href]"):
            heading = link.css_first("h3")
            title = _clean(heading.text()) if heading is not None else ""
            url = quote(urljoin(response.url, (link.attributes.get("href") or "").strip()), safe=":/?&=#%()")
            parts = urlsplit(url)
            if not fold(title).startswith("bases reguladoras"):
                continue
            if parts.hostname in _HOSTS and parts.path.lower().endswith(".pdf") and _PRIVATE_PATH not in parts.path:
                found.setdefault(url, title)
        return [DocumentoRef(url, title, len(found) == 1) for url, title in found.items()]

    def selector_hash(self) -> str:
        return ", ".join((_LISTING_BLOCK, *_SECTIONS))


# -- page helpers ------------------------------------------------------------------------------


def _clean(text: str) -> str:
    return " ".join(text.replace("​", "").replace("﻿", "").replace("\xa0", " ").split())


def _tree(response: Response) -> LexborHTMLParser:
    tree = LexborHTMLParser(response.text)
    tree.strip_tags(["script", "style", "noscript", "template"])
    return tree


def _promotion_page(response: Response, url: str) -> LexborHTMLParser:
    tree = _tree(response)
    if tree.css_first("section.inn-banner h1") is None or tree.css_first("section.sorito-sec") is None:
        raise ValueError(f"EMSV Getafe: la ficha no tiene el formato esperado: {url}")
    return tree


def _state(tree: LexborHTMLParser) -> tuple[str, str | None, str | None]:
    """(estado, evidence, lottery date) from the link titles. Open registration is never inferred."""
    titles = [_clean(node.text()) for node in tree.css("section.sorito-sec a h3")]
    results = [(title, m) for title in titles if (m := _RESULT.fullmatch(fold(title)))]
    if results:
        title, match = results[0]
        sorteo = None
        if len(results) == 1 and match["d"]:
            try:
                sorteo = date(int(match["y"]), int(match["m"]), int(match["d"])).isoformat()
            except ValueError:
                sorteo = None
        return "sorteo_adjudicacion", title, sorteo
    steps = [_clean(node.text()) for node in tree.css("section.grupo-cont-sec a p")]
    for step in steps:
        if _LOTTERY_STEP.search(fold(step)):
            return "sorteo_adjudicacion", step, None
    return "desconocido", None, None


def _requirements(tree: LexborHTMLParser, ine: str, requisitos: dict[str, Any], note) -> None:
    """Municipal registration plus, as text, the lottery groups and the conditions in the FAQ."""
    answers: list[str] = []
    for node in tree.css("section.faqs-sc-container .ea-body"):
        answer = _clean(node.text()).removeprefix("->").strip()
        if answer and answer not in answers:
            answers.append(answer)

    residence = [(answer, m) for answer in answers if (m := _RESIDENCE.search(fold(answer)))]
    shapes = {(bool(m["continuous"]), bool(m["only"])) for _, m in residence}
    if len(shapes) == 1:
        continuous, only = shapes.pop()
        requisitos["empadronamiento"] = {
            "ambito": "municipio",
            "municipio_ine": ine,
            "anios_min": None,  # stated as a date, not as a number of years
            "ininterrumpido": True if continuous else None,
            "alternativa_trabajo": False if only else None,
        }
        note("/requisitos/empadronamiento", residence[0][0])

    otros: list[str] = []
    for group in tree.css("section.grupo-cont-sec li.title-li"):
        number, description = group.css_first("h3"), group.css_first("h4")
        if number is not None and description is not None:
            otros.append(f"{_clean(number.text())}: {_clean(description.text())}")
    for answer in answers:
        if any(pattern.search(fold(answer)) for pattern in _OTHER_CONDITIONS):
            otros.append(answer if len(answer) <= _MAX_OTRO else answer[: _MAX_OTRO - 1] + "…")
    otros = list(dict.fromkeys(item[:_MAX_OTRO] for item in otros))
    if otros:
        requisitos["otros"] = otros
        note("/requisitos/otros", " | ".join(otros))
