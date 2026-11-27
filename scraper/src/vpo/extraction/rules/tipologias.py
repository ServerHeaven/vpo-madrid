"""Helpers for ``/tipologias``: header recognition, row -> tipologia dict and aggregation. No extractor."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ..base import Document, Table, plegar
from ..patterns import NUM_RE, to_number
from ..patterns import rentas as p

SIN_ANEJO = {"disponibilidad": "desconocido", "precio_mensual_eur": None}
MAX_FILAS_CABECERA = 4
PRECIO_ANEJO = (5.0, 300.0)


def nueva(
    dormitorios: int | None = None,
    superficie: float | None = None,
    renta: float | None = None,
    renta_max: float | None = None,
    num_viviendas: int | None = None,
    garaje: dict | None = None,
    trastero: dict | None = None,
    adaptada: bool | None = None,
) -> dict[str, Any]:
    """A full tipologia object (all eight schema keys)."""
    return {
        "dormitorios": dormitorios,
        "superficie_util_m2": superficie,
        "renta_mensual_eur": renta,
        "renta_mensual_max_eur": renta_max if renta_max != renta else None,
        "num_viviendas": num_viviendas,
        "garaje": dict(garaje or SIN_ANEJO),
        "trastero": dict(trastero or SIN_ANEJO),
        "adaptada_pmr": adaptada,
    }


def ordenar(tipologias: list[dict]) -> list[dict]:
    """Sorted by (dormitorios, superficie_util_m2); unknown first."""

    def key(row: dict) -> tuple:
        values = (row["dormitorios"], row["superficie_util_m2"], row["renta_mensual_eur"])
        return tuple(-1 if v is None else v for v in values)

    return sorted(tipologias, key=key)


def limpiar(celda: str | None) -> str:
    """A cell as one folded line; words hyphenated across lines are joined."""
    text = re.sub(r"(?<=[^\W\d])-[ \t]*\n\s*(?=[^\W\d])", "", celda or "")
    return " ".join(plegar(text).split())


# -- header -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Columnas:
    dormitorios: int | None
    tipologia: int | None
    renta: int
    renta_max: int | None = None
    renta_alternativas: tuple[int, ...] = ()  # must agree with ``renta`` in every row
    superficie: int | None = None
    num_viviendas: int | None = None
    garaje: int | None = None
    trastero: int | None = None
    garaje_modo: str = "desconocido"
    trastero_modo: str = "desconocido"
    individual: bool = False  # one row per dwelling


def _es_dato(celda: str) -> bool:
    return bool(
        re.match(rf"(?:(?:desde|de) )?{NUM_RE}\s*(?:€|euros)?(?:$|\s*[-–*(/]|\s+(?:a|y|hasta)\s)", celda)
        or p.CELDA_TIPOLOGIA.match(celda)
        or celda == "estudio"
    )


def separar_cabecera(filas: Sequence[Sequence[str]]) -> tuple[str, list[str], int]:
    """(title, one heading per column, index of the first data row).

    Index 0 means the table has no header (a continuation from the previous page).
    """
    width = max((len(row) for row in filas), default=0)
    rows = [[*row, *[""] * (width - len(row))] for row in filas]
    start = next((i for i, row in enumerate(rows) if any(_es_dato(c) for c in row)), len(rows))
    if start == 0:
        return "", [""] * width, 0
    if start > MAX_FILAS_CABECERA or start >= len(rows):
        return "", [""] * width, len(rows)
    header = rows[:start]
    titles: list[str] = []
    # A lone first cell is a title unless the row below leaves its column empty (vertical merge).
    while len(header) > 1 and width > 1 and header[0][0] and not any(header[0][1:]) and header[1][0]:
        titles.append(header.pop(0)[0])
    filled = [list(row) for row in header]
    for i, row in enumerate(filled[:-1]):
        # A merged group heading spans the following columns that have a sub-heading.
        for col in range(1, width):
            if not row[col] and row[col - 1] and any(lower[col] for lower in header[i + 1 :]):
                row[col] = row[col - 1]
    headings = [" ".join(row[col] for row in filled if row[col]) for col in range(width)]
    return " ".join(titles), headings, start


def _es_columna_renta(heading: str, title: str) -> bool:
    if p.CAB_NO_RENTA.search(heading):
        return False
    if p.CAB_GASTOS.search(heading) and "incluid" not in heading:
        return False
    if not p.CAB_RENTA_FUERTE.search(heading):
        if not (p.CAB_RENTA_DEBIL.search(heading) and p.CAB_MENSUAL.search(f"{heading} {title}")):
            return False
    # "renta garaje" is the price of an annex, not a dwelling rent.
    return not (p.CAB_ANEJO.search(heading) and not p.CAB_COMBINADA.search(heading))


def _columna_anejo(headings: Sequence[str], used: set, own: re.Pattern, other: re.Pattern) -> tuple[int | None, str]:
    """(column, mode) of the garage or storage column; "presencia:" marks a column without a price word."""
    for i, h in enumerate(headings):
        if i in used or not own.search(h) or other.search(h) or p.CAB_COMBINADA.search(h):
            continue
        priced = bool(p.CAB_PRECIO_ANEJO.search(h)) and not p.CAB_NO_PRECIO_ANEJO.search(h)
        if not (priced or p.CAB_SOLO_ANEJO.match(h)):
            continue
        mode = "desconocido"
        if "opcional" in h or "no vinculad" in h:
            mode = "opcional"
        elif re.search(r"(?<!no )\b(?:incluid|vinculad)", h) and "iva" not in h:
            mode = "incluido"
        return i, mode if priced else f"presencia:{mode}"
    return None, "desconocido"


def reconocer_columnas(title: str, headings: list[str], datos: Sequence[Sequence[str]]) -> Columnas | None:
    """Which column is which, or None if this is not a table of dwelling rents."""
    if p.TITULO_EXCLUIDO.search(title):
        return None
    rents = [i for i, h in enumerate(headings) if _es_columna_renta(h, title)]
    if not rents:
        return None

    def _column(i: int) -> list[str]:
        return [row[i] for row in datos if i < len(row) and row[i]]

    bedrooms = next(
        (
            i
            for i, h in enumerate(headings)
            if i not in rents and p.CAB_DORMITORIOS.search(h) and not p.CAB_UTIL.search(h)
        ),
        None,
    )
    typology = next(
        (
            i
            for i, h in enumerate(headings)
            if i not in rents
            and i != bedrooms
            and (
                p.CAB_TIPOLOGIA.search(h)
                or ((not h or p.CAB_VIVIENDA.match(h)) and any(p.CELDA_TIPOLOGIA.search(c) for c in _column(i)))
            )
        ),
        None,
    )
    if bedrooms is None and typology is None:
        return None

    # Several rent columns: keep the plain dwelling rent, or a min / max pair.
    plain = [i for i in rents if not (p.CAB_ANEJO.search(headings[i]) or "total" in headings[i])]
    rents = plain or rents
    rent_max, alternatives = None, ()
    if len(rents) > 1:
        low = [i for i in rents if p.CAB_MINIMA.search(headings[i]) and not p.CAB_MAXIMA.search(headings[i])]
        high = [i for i in rents if p.CAB_MAXIMA.search(headings[i]) and not p.CAB_MINIMA.search(headings[i])]
        if len(rents) == 2 and len(low) == 1 and len(high) == 1:
            rents, rent_max = low, high[0]
        else:
            alternatives = tuple(rents[1:])
    rent = rents[0]
    used = {rent, rent_max, bedrooms, typology, *alternatives}

    surfaces = [
        i
        for i, h in enumerate(headings)
        if i not in used and p.CAB_UTIL.search(h) and not p.CAB_NO_UTIL.search(h)
    ]
    count = next(
        (
            i
            for i, h in enumerate(headings)
            if i not in used
            and p.CAB_NUM_VIVIENDAS.search(h)
            and not p.CAB_RENTA_FUERTE.search(h)
            and not any(p.CELDA_TIPOLOGIA.search(c) for c in _column(i))
        ),
        None,
    )
    used |= {count, *surfaces}
    garage, garage_mode = _columna_anejo(headings, used, p.CAB_GARAJE, p.CAB_TRASTERO)
    storage, storage_mode = _columna_anejo(headings, used, p.CAB_TRASTERO, p.CAB_GARAJE)
    individual = count is None and any(
        i not in used and (p.CAB_IDENTIFICADOR.search(h) or (p.CAB_VIVIENDA.match(h) and _column(i)))
        for i, h in enumerate(headings)
    )
    return Columnas(
        dormitorios=bedrooms,
        tipologia=typology,
        renta=rent,
        renta_max=rent_max,
        renta_alternativas=alternatives,
        superficie=surfaces[0] if len(surfaces) == 1 else None,
        num_viviendas=count,
        garaje=garage,
        trastero=storage,
        garaje_modo=garage_mode,
        trastero_modo=storage_mode,
        individual=individual,
    )


# -- cells --------------------------------------------------------------------------------------


def leer_dormitorios(celda: str, *, columna_dormitorios: bool) -> int | None:
    """Bedrooms in a cell. A bare digit only counts under a "dormitorios" heading."""
    if not celda or p.CELDA_VARIAS.search(celda):
        return None
    found = {int(to_number(m["d"]) or 0) for m in p.CELDA_TIPOLOGIA.finditer(celda)}
    if len(found) == 1:
        value = found.pop()
    elif found:
        return None
    elif p.CELDA_ESTUDIO.search(celda):
        value = 0
    elif columna_dormitorios:
        bare = re.fullmatch(r"([0-6])(?:\s*\(\*?\d?\))?\*?", celda)
        if bare:
            value = int(bare[1])
        elif celda in ("uno", "dos", "tres", "cuatro"):
            value = int(to_number(celda) or 0)
        else:
            return None
    else:
        return None
    return value if 0 <= value <= 6 else None


def leer_importe(celda: str) -> tuple[float, float | None] | None:
    """'600,50 €/mes' -> (600.5, None); '600 - 700' -> (600, 700). Anything else -> None."""
    text = re.sub(r"\(\s*\*?\d?\s*\)|\*", " ", celda)
    numbers = [to_number(n) for n in re.findall(NUM_RE, text)]
    rest = re.sub(NUM_RE, " # ", text)
    rest = re.sub(r"€|\beuros?\b|\beur\b|/\s*mes\b|\bal mes\b|\bmensual(?:es)?\b|\bmes\b", " ", rest)
    rest = " ".join(rest.split())
    # "Desde 600" states the minimum rent, which is what renta_mensual_eur holds.
    if len(numbers) == 1 and rest in ("#", "desde #") and numbers[0] is not None:
        return numbers[0], None
    if len(numbers) == 2 and re.fullmatch(r"(?:(?:desde|de|entre) )?# ?(?:-|–|—|a|y|hasta) ?#", rest):
        low, high = numbers
        if low is not None and high is not None and low < high:
            return low, high
    return None


def leer_superficie(celda: str) -> float | None:
    match = re.fullmatch(rf"(\d+\.\d{{1,2}}|{NUM_RE})\s*(?:m2|m 2|metros)?", celda)
    if not match:
        return None
    text = match[1]
    value = float(text) if re.fullmatch(r"\d+\.\d{1,2}", text) else to_number(text)
    return value if value is not None and 15 <= value <= 200 else None


def leer_entero(celda: str) -> int | None:
    if not re.fullmatch(r"\d{1,4}", celda):
        return None
    return int(celda) or None


def leer_anejo(celda: str, modo: str) -> dict[str, Any]:
    """A garage / storage cell. ``modo`` comes from the heading."""
    presence = modo.startswith("presencia:")
    mode = modo.removeprefix("presencia:")
    if re.fullmatch(r"incluid[oa]s?(?: en (?:la )?renta| en el precio)?", celda):
        return {"disponibilidad": "incluido", "precio_mensual_eur": None}
    if celda in ("opcional", "no"):
        return {"disponibilidad": celda, "precio_mensual_eur": None}
    amount = leer_importe(celda)
    # A bare number under a heading with no price word may well be a count.
    if amount and amount[1] is None and (not presence or re.search(r"€|euro", celda)):
        if PRECIO_ANEJO[0] <= amount[0] <= PRECIO_ANEJO[1]:
            return {"disponibilidad": mode, "precio_mensual_eur": amount[0]}
    return dict(SIN_ANEJO)


# -- rows ---------------------------------------------------------------------------------------


def _celda(row: Sequence[str], index: int | None) -> str:
    return row[index] if index is not None and index < len(row) else ""


@dataclass
class Tabla:
    """One rent table, possibly spread over consecutive pages."""

    pagina: int
    columnas: Columnas
    ancho: int
    evidencia: str
    clave: tuple[str, ...] = ()  # headings of the columns read: equal keys describe the same data
    filas: list[dict] = field(default_factory=list)
    arrastre: int | None = None  # bedrooms of the last row, for vertically merged cells
    continuada: bool = False
    invalida: bool = False  # a row with a rent could not be understood

    def anadir(self, datos: Sequence[Sequence[str]]) -> None:
        cols = self.columnas
        for row in datos:
            if not any(row) or any(p.CELDA_FILA_RESUMEN.search(c) for c in row):
                continue
            bed_cell, type_cell = _celda(row, cols.dormitorios), _celda(row, cols.tipologia)
            bedrooms = leer_dormitorios(bed_cell, columna_dormitorios=True)
            if bedrooms is None:
                bedrooms = leer_dormitorios(type_cell, columna_dormitorios=False)
            rent_cell = _celda(row, cols.renta)
            rent = leer_importe(rent_cell)
            if bedrooms is None:
                if any(p.CELDA_FILA_AJENA.search(c) for c in row):
                    continue
                if bed_cell or type_cell:
                    self.invalida |= rent is not None
                    continue
                if rent is None or self.arrastre is None:
                    continue
                bedrooms = self.arrastre
            self.arrastre = bedrooms
            if any(_celda(row, i) != rent_cell for i in cols.renta_alternativas):
                self.invalida = True  # e.g. rent with and without VAT: which one is it?
            low, high = rent if rent else (None, None)
            if cols.renta_max is not None:
                maximum = leer_importe(_celda(row, cols.renta_max))
                high = maximum[0] if maximum and maximum[1] is None else None
                if low is not None and high is not None and high < low:
                    self.invalida = True
            self.filas.append(
                nueva(
                    bedrooms,
                    leer_superficie(_celda(row, cols.superficie)),
                    low,
                    high,
                    leer_entero(_celda(row, cols.num_viviendas)),
                    leer_anejo(_celda(row, cols.garaje), cols.garaje_modo),
                    leer_anejo(_celda(row, cols.trastero), cols.trastero_modo),
                    True if any(p.CELDA_ADAPTADA.search(c) for c in (bed_cell, type_cell)) else None,
                )
            )

    def tipologias(self) -> list[dict]:
        """Empty when the table gives no usable rent."""
        if self.invalida or not any(row["renta_mensual_eur"] is not None for row in self.filas):
            return []
        return ordenar(agregar(self.filas) if self.columnas.individual else self.filas)


def agregar(filas: Sequence[dict]) -> list[dict]:
    """A list of individual dwellings -> one entry per number of bedrooms."""
    groups: dict[int | None, list[dict]] = {}
    for row in filas:
        groups.setdefault(row["dormitorios"], []).append(row)

    def _same(rows: list[dict], key: str) -> Any:
        first = rows[0][key]
        return first if all(row[key] == first for row in rows) else None

    result = []
    for bedrooms, rows in groups.items():
        lows = [row["renta_mensual_eur"] for row in rows]
        known = all(value is not None for value in lows)
        highs = [row["renta_mensual_max_eur"] or row["renta_mensual_eur"] for row in rows]
        result.append(
            nueva(
                bedrooms,
                _same(rows, "superficie_util_m2"),
                min(lows) if known else None,
                max(highs) if known else None,
                len(rows),
                _same(rows, "garaje"),
                _same(rows, "trastero"),
                _same(rows, "adaptada_pmr"),
            )
        )
    return result


def _limpiar_tabla(table: Table) -> list[list[str]]:
    width = max((len(row) for row in table), default=0)
    rows = [[limpiar(c) for c in row] + [""] * (width - len(row)) for row in table]
    rows = [row for row in rows if any(row)]
    # pdfplumber often yields columns that are empty throughout.
    keep = [i for i in range(width) if any(row[i] for row in rows)]
    return [[row[i] for i in keep] for row in rows]


def tablas_de_renta(doc: Document) -> list[Tabla]:
    """Every rent table of the document; headerless continuations join the previous one."""
    found: list[Tabla] = []
    previous: Tabla | None = None  # last table of the page just read, if it was a rent table
    previous_page = 0
    for page in doc.paginas:
        for position, table in enumerate(page.tablas):
            rows = _limpiar_tabla(table)
            title, headings, start = separar_cabecera(rows) if rows else ("", [], len(rows))
            if rows and start == 0 and previous and position == 0 and page.numero == previous_page + 1:
                if len(headings) == previous.ancho:
                    previous.anadir(rows)
                    previous.continuada = True
                    previous_page = page.numero
                    continue
            previous = None
            if start == 0 or start >= len(rows):
                continue
            data = rows[start:]
            columns = reconocer_columnas(title, headings, data)
            if columns is None:
                continue
            evidence = " ; ".join(" | ".join(row) for row in [headings, *data[:3]])
            used = (columns.dormitorios, columns.tipologia, columns.renta, columns.renta_max, columns.num_viviendas)
            key = tuple("" if i is None else headings[i] for i in used)
            previous = Tabla(page.numero, columns, len(headings), f"{title} {evidence}".strip(), key)
            previous.anadir(data)
            previous_page = page.numero
            found.append(previous)
    return found
