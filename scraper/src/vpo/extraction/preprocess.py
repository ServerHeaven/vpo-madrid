"""Text preprocessing of a ``Document`` (ARCHITECTURE.md §5.2). No IO.

Step 1 (scan detection) happens in ``documents/pdf.py``. ``preparar`` does the rest: Unicode
normalisation, removal of repeated headers and footers, paragraph reconstruction with
de-hyphenation, the folded search copy, sections and the normative-citation flag.

A paragraph belongs to the page where it starts, even when it continues on the next one.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace

from .base import SEPARADOR_PARRAFOS, Document, Page, Paragraph, Section, Table, plegar

# Header / footer removal.
MIN_PAGINAS_CABECERA = 3  # shorter documents keep every line
FRACCION_CABECERA = 0.6  # repeated on more than this share of the pages
LINEAS_BORDE = 6  # only the first and last lines of a page are candidates

# NFKC keeps typographic quotes and dashes-like hyphens, so they are mapped by hand.
_SUSTITUCIONES = str.maketrans(
    {
        **dict.fromkeys("‘’‚‛", "'"),
        **dict.fromkeys("“”„‟«»", '"'),
        **dict.fromkeys("‐‑", "-"),
        **dict.fromkeys("", "•"),  # Symbol / Wingdings bullets
        **dict.fromkeys("​‌‍⁠﻿", None),
    }
)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


# -- 2. characters and spaces ---------------------------------------------------------------


def normalizar_unicode(linea: str) -> str:
    """NFKC, straight quotes, no invisible characters. A final soft hyphen becomes "-"."""
    linea = _CONTROL.sub(" ", unicodedata.normalize("NFKC", linea).translate(_SUSTITUCIONES)).rstrip()
    if linea.endswith("­"):
        linea = linea[:-1] + "-"
    return linea.replace("­", "")


def colapsar_espacios(linea: str) -> str:
    return " ".join(linea.split())


def _limpiar_lineas(texto: str) -> list[str]:
    lineas = (colapsar_espacios(normalizar_unicode(linea)) for linea in texto.split("\n"))
    return [linea for linea in lineas if linea]


# -- 3. de-hyphenation and line joining -----------------------------------------------------


def _corta_palabra(linea: str) -> bool:
    return len(linea) > 1 and linea.endswith("-") and linea[-2].isalnum()


def unir_lineas(lineas: Sequence[str]) -> str:
    """Join the lines of one paragraph, undoing end-of-line hyphenation.

    "vivien-" + "da" -> "vivienda". The hyphen is kept when what follows does not start with a
    lowercase letter ("Fuencarral-El Pardo", "2025-2026").
    """
    texto = ""
    for linea in lineas:
        if not texto:
            texto = linea
        elif _corta_palabra(texto):
            texto = (texto[:-1] if texto[-2].isalpha() and linea[:1].islower() else texto) + linea
        else:
            texto = f"{texto} {linea}"
    return texto


# -- 4. repeated headers and footers --------------------------------------------------------


def _claves_linea(linea: str, pagina: int) -> set[str]:
    """The folded line, plus variants where one number is expressed relative to the page.

    "Pág. 45" on page 3 and "Pág. 46" on page 4 share the variant with offset +42, while
    figures that do not advance with the pages never match each other.
    """
    plegada = plegar(linea)
    claves = {plegada}
    for numero in re.finditer(r"\d{1,6}", plegada):
        claves.add(f"{plegada[: numero.start()]}<{int(numero[0]) - pagina:+d}>{plegada[numero.end() :]}")
    return claves


def lineas_repetidas(paginas: Sequence[Sequence[str]]) -> list[set[int]]:
    """Per page, the indexes of the header and footer lines repeated on most pages."""
    total = len(paginas)
    if total < MIN_PAGINAS_CABECERA:
        return [set() for _ in paginas]
    candidatas: list[dict[int, set[str]]] = []
    apariciones: dict[str, set[int]] = defaultdict(set)
    for numero, lineas in enumerate(paginas, 1):
        borde = {i for i in range(len(lineas)) if i < LINEAS_BORDE or i >= len(lineas) - LINEAS_BORDE}
        propias = {i: _claves_linea(lineas[i], numero) for i in sorted(borde)}
        candidatas.append(propias)
        for claves in propias.values():
            for clave in claves:
                apariciones[clave].add(numero)
    return [
        {i for i, claves in propias.items() if any(len(apariciones[c]) > FRACCION_CABECERA * total for c in claves)}
        for propias in candidatas
    ]


# -- 3 bis. paragraphs ----------------------------------------------------------------------

# Words after which a sentence cannot end (folded).
_CONECTORES = frozenset(
    "a al cada como con cuyo cuya de del desde e el en entre esta este estas estos hasta la las lo los mas "
    "menos ni no o para por que se segun sin sobre su sus u un una unas unos veces y sea sean sera seran "
    "podra podran debera deberan".split()
)
_ABREVIATURA = re.compile(r"(?:^|[\s(])(?:art|arts|num|n|pag|d|da|dna|sr|sra|avda|ap|aprox|excmo|ilmo)\.$")
_MARCADOR = (
    r"(?:[•◦▪■□●○‣∙·➢➤►▶✓✔❖❑]|[-–—*](?=\s|$)|\d{1,2}(?:[.)]|\.-)(?=\s|$)|\d{1,2}\.?[ao]\)"
    r"|\d{1,2}(?:\.\d{1,2})+\.?-?(?=\s+[A-ZÁÉÍÓÚÑ\"¿])|\(?[a-zA-ZñÑ]\)|\([0-9ivx]{1,3}\)|[ivx]{2,4}[.)](?=\s))"
)
_INICIO_LISTA = re.compile(rf"^{_MARCADOR}")
_SOLO_MARCADOR = re.compile(rf"^{_MARCADOR}$")
_ORDINAL = r"(?:primer[ao]|segund[ao]|tercer[ao]|cuart[ao]|quint[ao]|sext[ao]|septim[ao]|octav[ao]|noven[ao]|" \
    r"(?:un|duo)?decim[ao](?:\s?(?:primer|segund|tercer|cuart|quint)[ao])?)"
# "BASE 3.a", "ARTICULO 5.", "3.", "3.1.", "IV.", "a)", "TERCERA.-" at the start of a title (folded).
_ENUMERACION = re.compile(
    rf"^(?:base\s+(?:\d{{1,2}}|[ivxl]+\b|{_ORDINAL})(?:\.?[ao]\b)?|\d{{1,2}}(?:\.\d{{1,2}})*(?:\.?[ao]\b)?"
    rf"|articulo\.?\s*\d{{1,3}}(?:\.?[ao]\b)?(?=\s*[.\-–—:])"
    rf"|[ivxl]{{1,5}}(?=[.)\-])|[a-z](?=\))|{_ORDINAL}(?=\s*[.\-–—:]))[\s.\-–—:)]*"
)
# "BASE n", "ANEXO n" and "ARTÍCULO n." as written at the start of a heading of this document.
_BASE_O_ANEXO = re.compile(
    rf"^(?:(?:BASE|Base)\s+(?:\d|[IVXL]+\b|(?i:{_ORDINAL}))|(?:ANEXO|Anexo)\b(?=\s*(?:$|[IVXL\d]+\b|[.\-–—:]))"
    r"|(?:ART[IÍ]CULO|Art[ií]culo)\.?\s*\d{1,3}(?:\.?[ºo]\b)?\s*[.\-–—:])"
)
_INDICE = re.compile(r"\.{4,}|(?:\. ){4,}|…{2,}")  # table of contents leaders


def _es_mayusculas(texto: str) -> bool:
    """An all-caps title, ignoring its enumeration."""
    resto = texto[_fin_enumeracion(texto) :]
    letras = [c for c in resto if c.isalpha()]
    return (
        len(letras) >= 6
        and all(c.isupper() for c in letras)
        and sum(c.isdigit() for c in resto) <= 4
        and not resto.endswith((";", ","))
    )


def _fin_enumeracion(texto: str) -> int:
    match = _ENUMERACION.match(plegar(texto))
    return match.end() if match else 0


def _es_titulo(linea: str) -> bool:
    """A line that stands on its own: all caps, "BASE n" or "ANEXO n"."""
    if len(linea) > 150 or _INDICE.search(linea):
        return False
    return _es_mayusculas(linea) or (bool(_BASE_O_ANEXO.match(linea)) and len(linea) <= 100)


def _queda_abierta(linea: str) -> bool:
    """The line ends in a way that requires more words."""
    if linea.endswith((",", "(")):
        return True
    ultima = plegar(linea).rsplit(" ", 1)[-1]
    return ultima in _CONECTORES


def _termina_frase(linea: str) -> bool:
    sin_cierre = linea.rstrip("\"')]")
    return sin_cierre.endswith((".", ":", ";", "!", "?")) and not _ABREVIATURA.search(plegar(sin_cierre))


def _corta_entre(anterior: str, linea: str, ancho: int) -> bool:
    """Whether a new paragraph starts at ``linea``, both lines being in the same block."""
    if _corta_palabra(anterior):
        return False
    abierta = _queda_abierta(anterior)
    # "Anexo I" in mixed case may be just the wrapped end of a sentence.
    envuelta = not (linea.isupper() or _termina_frase(anterior) or len(anterior) < 0.75 * ancho)
    if _es_titulo(linea) and not (abierta or envuelta):
        # A title wrapped over two lines stays whole.
        if _es_titulo(anterior) and not _termina_frase(anterior) and not _BASE_O_ANEXO.match(linea):
            return bool(_INICIO_LISTA.match(linea))
        return True
    if _es_titulo(anterior) and not abierta and not linea[0].islower():
        return True
    if _INICIO_LISTA.match(linea) and not abierta:
        return True
    if _INDICE.search(anterior):
        return True
    if linea[0].islower() or not _termina_frase(anterior):
        return False
    return anterior.endswith(":") or len(anterior) < 0.75 * ancho


def dividir_bloque(lineas: Sequence[str], ancho: int) -> list[list[str]]:
    """Split the lines of a block into paragraphs. ``ancho``: usual line length of the page."""
    trozos: list[list[str]] = []
    for linea in lineas:
        if trozos and not _corta_entre(trozos[-1][-1], linea, ancho):
            trozos[-1].append(linea)
        else:
            trozos.append([linea])
    return trozos


@dataclass
class _Trozo:
    lineas: list[str]
    pagina: int
    bbox: tuple[float, float, float, float] | None  # None: blank-line delimited text
    alto: float = 0.0  # height of one line
    ultima_pagina: int = 0


def _misma_fila(anterior: _Trozo, siguiente: _Trozo) -> bool:
    if anterior.bbox is None or siguiente.bbox is None or anterior.ultima_pagina != siguiente.pagina:
        return False
    if len(anterior.lineas) != 1 or len(siguiente.lineas) != 1:
        return False
    solape = min(anterior.bbox[3], siguiente.bbox[3]) - max(anterior.bbox[1], siguiente.bbox[1])
    return solape > 0.5 * min(anterior.alto, siguiente.alto) and siguiente.bbox[0] >= anterior.bbox[2] - 1


def _continua(anterior: _Trozo, siguiente: _Trozo, ancho: int) -> bool:
    """Whether ``siguiente``, a different block, is the rest of the paragraph ``anterior``."""
    final, inicio = anterior.lineas[-1], siguiente.lineas[0]
    mismo_lugar = anterior.ultima_pagina == siguiente.pagina
    if anterior.bbox is None or siguiente.bbox is None:
        if mismo_lugar:  # a blank line is a real paragraph break
            return False
    if _corta_palabra(final) and inicio[0].islower():
        return True
    if len(anterior.lineas) == 1 and _SOLO_MARCADOR.match(final):
        return True
    if _INDICE.search(final) or _termina_frase(final):
        return False
    abierta = _queda_abierta(final)
    if (_es_titulo(inicio) or _INICIO_LISTA.match(inicio)) and not abierta:
        return False
    if _es_titulo(final) and not abierta and not inicio[0].islower():
        return False
    # A wide vertical gap separates paragraphs. A jump upwards is a column break.
    if mismo_lugar and anterior.bbox and siguiente.bbox:
        if siguiente.bbox[1] - anterior.bbox[3] > 2 * max(anterior.alto, siguiente.alto):
            return False
    return inicio[0].islower() or abierta or len(final) >= max(0.75 * ancho, 40)


def _unir_trozos(previo: _Trozo, nuevo: _Trozo, *, fila: bool) -> None:
    """Extend ``previo`` with ``nuevo``. Pieces of one visual row become a single line."""
    if fila:
        previo.lineas = [unir_lineas([*previo.lineas, nuevo.lineas[0]]), *nuevo.lineas[1:]]
    else:
        previo.lineas = [*previo.lineas, *nuevo.lineas]
        previo.alto = nuevo.alto
    if previo.bbox and nuevo.bbox:
        arriba = min(previo.bbox[1], nuevo.bbox[1]) if fila else nuevo.bbox[1]
        previo.bbox = (
            min(previo.bbox[0], nuevo.bbox[0]),
            arriba,
            max(previo.bbox[2], nuevo.bbox[2]),
            nuevo.bbox[3],
        )
    previo.ultima_pagina = nuevo.ultima_pagina


def _ancho_usual(lineas: Sequence[str]) -> int:
    largos = sorted(map(len, lineas))
    return largos[int(0.9 * (len(largos) - 1))] if largos else 0


def _trozos_de_pagina(pagina: Page) -> list[_Trozo]:
    """The blocks of a page as lists of clean lines (``pagina.texto`` when there are none)."""
    if pagina.bloques:
        crudos = [(b.bbox, b.texto) for b in pagina.bloques]
    else:
        crudos = [(None, texto) for texto in re.split(r"\n[ \t]*\n", pagina.texto)]
    trozos = []
    for bbox, texto in crudos:
        lineas = _limpiar_lineas(texto)
        if lineas:
            alto = (bbox[3] - bbox[1]) / len(lineas) if bbox else 0.0
            trozos.append(_Trozo(lineas, pagina.numero, bbox, alto, pagina.numero))
    return trozos


def reconstruir_parrafos(paginas: Sequence[Page]) -> list[tuple[int, str]]:
    """(page, text) of every paragraph, without repeated headers and footers."""
    por_pagina = [_trozos_de_pagina(p) for p in paginas]
    planas = [[linea for trozo in trozos for linea in trozo.lineas] for trozos in por_pagina]
    sobrantes = lineas_repetidas(planas)

    parrafos: list[_Trozo] = []
    anchos: list[int] = []  # usual line length where each paragraph ends
    for trozos, lineas_pagina, quitar in zip(por_pagina, planas, sobrantes, strict=True):
        ancho = _ancho_usual([linea for i, linea in enumerate(lineas_pagina) if i not in quitar])
        indice = 0
        for trozo in trozos:
            lineas = [linea for i, linea in enumerate(trozo.lineas, indice) if i not in quitar]
            indice += len(trozo.lineas)
            for numero, parte in enumerate(dividir_bloque(lineas, ancho)):
                nuevo = replace(trozo, lineas=parte)
                # Parts of one block were already split on purpose: only the first one may continue.
                previo = parrafos[-1] if numero == 0 and parrafos else None
                fila = previo is not None and _misma_fila(previo, nuevo)
                if previo is not None and (fila or _continua(previo, nuevo, anchos[-1])):
                    _unir_trozos(previo, nuevo, fila=fila)
                    anchos[-1] = ancho
                else:
                    parrafos.append(nuevo)
                    anchos.append(ancho)
    return [(p.pagina, unir_lineas(p.lineas)) for p in parrafos]


# -- 6. sections ----------------------------------------------------------------------------

_CLAVES_SECCION = (
    ("anexo", r"^anexos?\b"),
    ("requisitos", r"requisitos?\b|condiciones de acceso|quienes? pued|empadronamiento|destinatarios|beneficiarios"
                   r"|(?:nivel de |limites? de )?ingresos\b"),
    ("plazos", r"plazos?\b(?!.*(?:duracion|contrato|arrendamiento))|presentacion de (?:las )?solicitudes"
               r"|calendario\b|inscripcion\b"),
    ("rentas", r"(?<!declaracion de la )(?<!declaracion de )(?<!impuesto sobre la )rentas?\b|regimen economico"
               r"|condiciones economicas|precios?\b|alquiler mensual"),
)
_MAX_TITULO = 120


def clasificar_encabezado(parrafo: str) -> tuple[bool, str | None] | None:
    """None when the paragraph is not a heading; otherwise (strong, section or None).

    Strong headings (all caps, "BASE n", "ANEXO", "TERCERA.-") close the previous section even
    when they name no known one. Weak ones ("4. Requisitos") only count when the title starts
    with a section keyword, so that list items never change the section.
    """
    if _INDICE.search(parrafo):
        return None
    resto = parrafo[_fin_enumeracion(parrafo) :]
    plegado = plegar(parrafo)
    base_o_anexo = bool(_BASE_O_ANEXO.match(parrafo))
    anexo = base_o_anexo and plegado.startswith("anexo")
    ordinal = bool(re.match(rf"{_ORDINAL}\s*[.\-–—:]", plegado)) and parrafo[:1].isupper()
    mayusculas = len(parrafo) <= 150 and _es_mayusculas(parrafo)
    if mayusculas and not base_o_anexo and resto.endswith(".") and len(resto.split()) > 6:
        mayusculas = False  # an emphatic sentence
    if anexo and not (mayusculas or (len(parrafo) <= 100 and not parrafo.endswith((".", ";", ",")))):
        return None

    if base_o_anexo or ordinal or mayusculas:
        # Run-in headings ("BASE 3. Requisitos. Podrán...") are classified by their title only.
        titulo = plegar(resto if anexo else re.split(r"\.(?:\s|-|$)|:", resto, maxsplit=1)[0])[:_MAX_TITULO]
        if anexo:
            return True, "anexo"
        seccion = next((s for s, patron in _CLAVES_SECCION if re.search(patron, titulo)), None)
        return True, seccion

    titulo = plegar(resto).rstrip(" .:")
    largo, palabras = (130, 20) if _numero_apartado(parrafo) else (90, 10)
    if len(parrafo) > largo or len(titulo.split()) > palabras or parrafo.endswith((";", ",")):
        return None
    if not resto[:1].isupper() or any(c.isdigit() for c in titulo) or ". " in titulo:
        return None
    for seccion, patron in _CLAVES_SECCION[1:]:
        if re.match(rf"(?:{patron})", titulo):
            return False, seccion
    return None


# A top-level numbered title: "3. Title", "III.-Title", "2) Title" (not "3.1.").
_APARTADO = re.compile(r"^(?:(\d{1,2})|([ivxl]{1,5}))\s*(?:\.\s?[\-–—]?|[\-–—]|\))(?!(?<=\.)[ao]\b)\s*(?=[^\d\s.\-])")


def _numero_apartado(parrafo: str) -> int | None:
    match = _APARTADO.match(plegar(parrafo))
    if match is None:
        return None
    if match[1]:
        return int(match[1])
    valores = [{"i": 1, "v": 5, "x": 10, "l": 50}[c] for c in match[2]]
    return sum(-v if v < siguiente else v for v, siguiente in zip(valores, [*valores[1:], 0], strict=True))


def entradas_de_indice(parrafos: Sequence[str]) -> set[int]:
    """Paragraphs of a table of contents: dot leaders, or a cluster of titles that all return later."""
    claves = []
    for parrafo in parrafos:
        resto = plegar(parrafo[_fin_enumeracion(parrafo) :])
        claves.append(re.sub(r"[\W_]+", " ", resto).strip() if len(parrafo) <= 200 else "")
    ultima = {clave: i for i, clave in enumerate(claves)}
    repetidas = {i for i, clave in enumerate(claves) if len(clave) >= 4 and ultima[clave] > i}
    indice = {i for i in repetidas if sum(j in repetidas for j in range(i - 2, i + 3)) >= 3}
    indice |= {i for i in range(1, len(parrafos) - 1) if i - 1 in indice and i + 1 in indice}
    return indice | {i for i, parrafo in enumerate(parrafos) if _INDICE.search(parrafo)}


def asignar_secciones(parrafos: Sequence[str]) -> list[str]:
    """One of base.SECCIONES for every paragraph. A heading belongs to the section it opens.

    A section opened by the numbered title "n." also ends at a short title numbered "n+1.".
    """
    indice = entradas_de_indice(parrafos)
    actual = "otros"
    apartado: int | None = None  # number of the title that opened the current section
    secciones = []
    for i, parrafo in enumerate(parrafos):
        encabezado = None if i in indice else clasificar_encabezado(parrafo)
        numero = _numero_apartado(parrafo)
        if i in indice:
            actual, apartado = "otros", None
        elif encabezado is not None and encabezado[1] is not None:
            actual, apartado = encabezado[1], numero
        elif encabezado is not None and encabezado[0]:
            if actual != "anexo" or plegar(parrafo).startswith("base "):
                actual, apartado = "otros", None
        elif apartado is not None and numero == apartado + 1:
            if len(parrafo) <= 120 and not parrafo.endswith((".", ";", ",")):
                actual, apartado = "otros", None
        secciones.append(actual)
    return secciones


# -- 7. normative citations -----------------------------------------------------------------

_INSTRUMENTO = (
    r"(?:real decreto(?:[- ]ley| legislativo)?\b|decreto(?:[- ]ley)?\b|ley(?: organica)?\b|reglamento\b"
    r"|texto refundido\b"
    r"|orden(?= (?:[a-z]{2,}/)?\d| ministerial))"
)
# An article or provision "of" an instrument (a bare "Artículo 5." is a heading of this document).
_ARTICULO = (
    r"(?:(?:articulos?|arts?\.) ?\d+(?:\.\d+)*(?:\.?o\b)?(?:(?:,| y| bis)(?: ?\d+(?:\.\d+)*)?)*"
    r"|disposicion (?:adicional|transitoria|final|derogatoria)(?: [a-z]+)?)"
    rf" de(?:l| la| el)? (?:(?:citad|mencionad|referid|vigente)[oa] )?{_INSTRUMENTO}"
)
_CITA = re.compile(rf"\b(?:{_ARTICULO}|{_INSTRUMENTO})")
_MARCO = (
    r"(?:de conformidad con|de acuerdo con|conforme (?:a|al|con)\b|segun|en virtud de|al amparo de"
    r"|en aplicacion de|en cumplimiento de|a tenor de|lo (?:dispuesto|establecido|previsto) en"
    r"|en los terminos (?:previstos|establecidos) en)"
)
# The paragraph opens by quoting legislation.
_ENCABEZA_CITA = re.compile(
    rf"(?:(?:asimismo|ademas|no obstante|por (?:su parte|otra parte|tanto)),? )?"
    rf"(?:{_MARCO}.{{0,60}}?\b|(?:el|la|los) )?(?:{_ARTICULO}|{_INSTRUMENTO})"
)
# It speaks about this very call: a requirement, even if it names a law in passing.
_PROPIA = re.compile(
    r"\bpresentes? (?:bases|convocatoria|procedimiento|promocion|sorteo|proceso)\b"
    r"|\best[ae]s? (?:bases|convocatoria|promocion|sorteo|procedimiento)\b"
    r"|\b(?:los|las) (?:personas )?solicitantes\b.{0,200}?\b(?:deberan|tendran que|habran de)\b"
    r"|\b(?:el|la) (?:persona )?solicitante\b.{0,200}?\b(?:debera|tendra que|habra de)\b"
)


def es_normativo(parrafo: str) -> bool:
    """Whether the paragraph quotes generic legislation rather than stating a rule of this call.

    True when it names a legal instrument, does not refer to this call ("las presentes bases",
    "los solicitantes deberán"), and either opens with the citation ("De conformidad con el
    Decreto...", "El artículo 5 del Reglamento...") or piles up three or more of them. A single
    citation in the middle or at the end of a statement is not penalised.
    """
    plegado = plegar(parrafo)
    cuerpo = plegado[_fin_enumeracion(parrafo) :].lstrip(" •-–—\"")
    citas = _CITA.findall(plegado)
    if not citas or _PROPIA.search(plegado):
        return False
    return len(citas) >= 3 or bool(_ENCABEZA_CITA.match(cuerpo))


# -- assembly -------------------------------------------------------------------------------


def limpiar_tabla(tabla: Table) -> Table:
    """The same normalisation as the running text, cell by cell."""
    return tuple(tuple(unir_lineas(_limpiar_lineas(celda)) for celda in fila) for fila in tabla)


def preparar(doc: Document) -> Document:
    """A copy of ``doc`` with ``texto``, ``busqueda``, ``parrafos``, ``secciones`` and clean tables."""
    bloques = reconstruir_parrafos(doc.paginas)
    textos = [texto for _, texto in bloques]
    nombres = asignar_secciones(textos)

    parrafos: list[Paragraph] = []
    inicio = 0
    for (pagina, texto), seccion in zip(bloques, nombres, strict=True):
        parrafos.append(Paragraph(inicio, inicio + len(texto), pagina, seccion, es_normativo(texto)))
        inicio += len(texto) + len(SEPARADOR_PARRAFOS)
    completo = SEPARADOR_PARRAFOS.join(textos)

    secciones = {}
    for nombre in dict.fromkeys(nombres):
        propios = [p for p in parrafos if p.seccion == nombre]
        secciones[nombre] = Section(
            propios[0].pagina,
            propios[-1].pagina,
            SEPARADOR_PARRAFOS.join(completo[p.inicio : p.fin] for p in propios),
        )

    paginas = tuple(replace(p, tablas=tuple(map(limpiar_tabla, p.tablas))) for p in doc.paginas)
    return replace(
        doc,
        paginas=paginas,
        texto=completo,
        busqueda=plegar(completo),
        parrafos=tuple(parrafos),
        secciones=secciones,
    )
