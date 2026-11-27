"""PDF bytes -> unprepared ``Document`` (ARCHITECTURE.md §5.1 and §5.2 step 1).

PyMuPDF gives the page text as blocks of visual lines in reading order; pdfplumber gives the
tables. Downloaded files are untrusted: neither library runs the scripts of a PDF or follows
its external references, and absurdly large documents are rejected before being read.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import pdfplumber
import pymupdf

from ...core.hashing import sha256_bytes
from ..base import Block, Document, Page, Table

MIN_CARACTERES_POR_PAGINA = 50  # below this average the document is a scan
MAX_PAGINAS = 300
MAX_BYTES = 50 * 1024 * 1024
MAX_CARACTERES = 3_000_000

# Two columns are assumed only when both halves of a page hold real prose, not table cells.
_ANCHO_MIN_COLUMNA = 0.28  # fraction of the page width
_CARACTERES_MIN_COLUMNA = 300

_log = logging.getLogger(__name__)


class DocumentoIlegible(ValueError):
    """The bytes are not a PDF that can be read."""


@dataclass
class _Linea:
    x0: float
    y0: float
    x1: float
    y1: float
    texto: str


def leer_pdf(data: bytes, url: str) -> Document:
    """Pages (text, blocks, tables), ``necesita_ocr`` and sha256. Not preprocessed."""
    if len(data) > MAX_BYTES:
        raise DocumentoIlegible(f"El PDF supera el tamaño máximo de {MAX_BYTES} bytes")
    if b"%PDF-" not in data[:1024]:
        raise DocumentoIlegible("El fichero no es un PDF")
    bloques = _leer_bloques(data)

    caracteres = sum(len("".join(b.texto.split())) for pagina in bloques for b in pagina)
    necesita_ocr = caracteres < MIN_CARACTERES_POR_PAGINA * len(bloques)
    tablas = [()] * len(bloques) if necesita_ocr else _leer_tablas(data, len(bloques))

    paginas = tuple(
        Page(numero, "\n\n".join(b.texto for b in pagina), pagina, tablas[numero - 1])
        for numero, pagina in enumerate(bloques, 1)
    )
    return Document(url=url, tipo="pdf", sha256=sha256_bytes(data), paginas=paginas, necesita_ocr=necesita_ocr)


# -- text (PyMuPDF) -------------------------------------------------------------------------


def _leer_bloques(data: bytes) -> list[tuple[Block, ...]]:
    try:
        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            if pdf.needs_pass:
                raise DocumentoIlegible("El PDF está protegido con contraseña")
            if pdf.page_count == 0:
                raise DocumentoIlegible("El PDF no tiene páginas legibles")
            if pdf.page_count > MAX_PAGINAS:
                raise DocumentoIlegible(f"El PDF tiene {pdf.page_count} páginas (máximo {MAX_PAGINAS})")
            paginas: list[tuple[Block, ...]] = []
            total = 0
            for pagina in pdf:
                bloques = _bloques_de_pagina(pagina)
                total += sum(len(b.texto) for b in bloques)
                if total > MAX_CARACTERES:
                    raise DocumentoIlegible(f"El PDF supera los {MAX_CARACTERES} caracteres")
                paginas.append(bloques)
            return paginas
    except DocumentoIlegible:
        raise
    except Exception as exc:  # MuPDF raises several unrelated types on corrupt input
        raise DocumentoIlegible(f"No se puede leer el PDF: {exc}") from exc


def _bloques_de_pagina(pagina: pymupdf.Page) -> tuple[Block, ...]:
    """Blocks in reading order. Rotated text (margin stamps) goes last so it never interleaves."""
    matriz = pagina.rotation_matrix  # text coordinates are given for the unrotated page
    horizontales: list[Block] = []
    girados: list[Block] = []
    for bloque in pagina.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]:
        lineas: list[_Linea] = []
        otras: list[_Linea] = []
        for linea in bloque.get("lines", ()):
            texto = "".join(span["text"] for span in linea["spans"])
            if not texto.strip():
                continue
            rect = pymupdf.Rect(linea["bbox"]) * matriz
            dx, dy = linea["dir"]
            direccion_x, direccion_y = dx * matriz.a + dy * matriz.c, dx * matriz.b + dy * matriz.d
            destino = lineas if direccion_x > 0 and abs(direccion_y) < 0.3 else otras
            destino.append(_Linea(rect.x0, rect.y0, rect.x1, rect.y1, texto.strip()))
        horizontales.extend(map(_bloque, _separar_lado_a_lado(_unir_fragmentos(lineas))))
        if otras:
            girados.append(_bloque(otras))
    return (*_ordenar(horizontales, pagina.rect.width), *girados)


def _unir_fragmentos(lineas: list[_Linea]) -> list[_Linea]:
    """Join the pieces of one visual line (justified text often comes split into several)."""
    unidas: list[_Linea] = []
    for linea in lineas:
        previa = unidas[-1] if unidas else None
        if previa is not None:
            solape = min(previa.y1, linea.y1) - max(previa.y0, linea.y0)
            alto = min(previa.y1 - previa.y0, linea.y1 - linea.y0)
            if solape > 0.5 * alto and -1 <= linea.x0 - previa.x1 <= 1.5 * alto:
                unidas[-1] = _Linea(
                    previa.x0,
                    min(previa.y0, linea.y0),
                    linea.x1,
                    max(previa.y1, linea.y1),
                    f"{previa.texto} {linea.texto}",
                )
                continue
        unidas.append(linea)
    return unidas


def _separar_lado_a_lado(lineas: list[_Linea]) -> list[list[_Linea]]:
    """MuPDF may put far apart columns or cells in one block: split what never overlaps sideways."""
    grupos: list[tuple[float, float, list[int]]] = []  # x0, x1, line indexes
    for indice, linea in enumerate(lineas):
        x0, x1, indices = linea.x0, linea.x1, [indice]
        resto = []
        for grupo in grupos:
            if x0 < grupo[1] and x1 > grupo[0]:
                x0, x1, indices = min(x0, grupo[0]), max(x1, grupo[1]), indices + grupo[2]
            else:
                resto.append(grupo)
        grupos = [*resto, (x0, x1, indices)]
    ordenados = sorted(sorted(indices) for _, _, indices in grupos)
    return [[lineas[i] for i in indices] for indices in ordenados]


def _bloque(lineas: list[_Linea]) -> Block:
    bbox = (
        round(min(l.x0 for l in lineas), 2),
        round(min(l.y0 for l in lineas), 2),
        round(max(l.x1 for l in lineas), 2),
        round(max(l.y1 for l in lineas), 2),
    )
    return Block(bbox, "\n".join(l.texto for l in lineas))


def _ordenar(bloques: list[Block], ancho: float) -> list[Block]:
    """Top to bottom and left to right; column by column on two-column pages (e.g. BOCM)."""
    izquierda = {b for b in bloques if b.bbox[2] <= 0.52 * ancho}
    derecha = {b for b in bloques if b.bbox[0] >= 0.48 * ancho}
    if not all(_es_columna(lado, ancho) for lado in (izquierda, derecha)):
        return _por_filas(bloques)

    # Full-width blocks cut the page into horizontal bands, each read left column first.
    orden: list[Block] = []
    banda: list[Block] = []

    def volcar() -> None:
        orden.extend(_por_filas([b for b in banda if b in izquierda]))
        orden.extend(_por_filas([b for b in banda if b not in izquierda]))
        banda.clear()

    for bloque in sorted(bloques, key=lambda b: (b.bbox[1], b.bbox[0])):
        if bloque in izquierda or bloque in derecha:
            banda.append(bloque)
        else:
            volcar()
            orden.append(bloque)
    volcar()
    return orden


def _es_columna(bloques: set[Block], ancho: float) -> bool:
    anchos = (b for b in bloques if b.bbox[2] - b.bbox[0] >= _ANCHO_MIN_COLUMNA * ancho)
    return sum(len(b.texto) for b in anchos) >= _CARACTERES_MIN_COLUMNA


def _por_filas(bloques: list[Block]) -> list[Block]:
    """Sort by vertical position; blocks starting at about the same height go left to right."""
    filas: list[list[Block]] = []
    for bloque in sorted(bloques, key=lambda b: (b.bbox[1], b.bbox[0], b.texto)):
        if filas:
            primero = filas[-1][0]
            alto = (primero.bbox[3] - primero.bbox[1]) / (primero.texto.count("\n") + 1)
            if bloque.bbox[1] - primero.bbox[1] <= min(0.5 * alto, 8.0):
                filas[-1].append(bloque)
                continue
        filas.append([bloque])
    return [b for fila in filas for b in sorted(fila, key=lambda b: (b.bbox[0], b.bbox[1], b.texto))]


# -- tables (pdfplumber) --------------------------------------------------------------------


def _leer_tablas(data: bytes, paginas: int) -> list[tuple[Table, ...]]:
    """Tables per page. A failure loses the tables of that page, never the document."""
    tablas: list[tuple[Table, ...]] = [()] * paginas
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for indice, pagina in enumerate(pdf.pages[:paginas]):
                try:
                    tablas[indice] = _normalizar_tablas(pagina.extract_tables())
                except Exception as exc:  # untrusted input: pdfminer fails in many ways
                    _log.warning("No se pueden leer las tablas de la página %d: %s", indice + 1, exc)
                finally:
                    pagina.close()  # frees the layout cache
    except Exception as exc:
        _log.warning("No se pueden leer las tablas del PDF: %s", exc)
    return tablas


def _normalizar_tablas(crudas: list[list[list[str | None]]]) -> tuple[Table, ...]:
    """Cells as str ("" when empty). Boxes holding fewer than two texts are not tables."""
    tablas: list[Table] = []
    for cruda in crudas:
        tabla = tuple(tuple((celda or "").strip() for celda in fila) for fila in cruda)
        tabla = tuple(fila for fila in tabla if any(fila))
        if sum(bool(celda) for fila in tabla for celda in fila) >= 2:
            tablas.append(tabla)
    return tuple(tablas)
