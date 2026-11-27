"""Rents and typologies: REG-RENTA-01..04 plus VAT / community fee notes (ARCHITECTURE.md §5.3)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, replace

from ..base import MAX_EVIDENCIA, Document, ExtractionContext, FieldResult
from ..patterns import to_number
from ..patterns import rentas as p
from . import tipologias as t

CAMPO = "/tipologias"
CAMPO_OTROS = "/requisitos/otros"
CONFIANZA_TABLA = 0.9
CONFIANZA_TABLA_CONTINUADA = 0.85
# A sentence ends at a full stop, except after the abbreviations used inside rent statements.
_FIN_FRASE = re.compile(r"(?<!dorm)(?<!dorms)(?<!aprox)(?<!\bn)(?<!\bnum)\.(?=\s|$)")


def frases(doc: Document) -> Iterator[tuple[int, str]]:
    """(offset in the document, folded sentence), never crossing a paragraph."""
    for paragraph in doc.parrafos:
        text = doc.busqueda[paragraph.inicio : paragraph.fin]
        start = 0
        for match in _FIN_FRASE.finditer(text):
            yield paragraph.inicio + start, text[start : match.end()]
            start = match.end()
        if start < len(text):
            yield paragraph.inicio + start, text[start:]


@dataclass(frozen=True)
class _Mencion:
    dormitorios: int | None
    superficie: float | None
    renta: float
    renta_max: float | None
    inicio: int
    fin: int


@dataclass(frozen=True)
class _Token:
    inicio: int
    fin: int
    dormitorios: int | None = None
    importe: tuple[float, float | None] | None = None


def _plausible(value: float | None) -> bool:
    return value is not None and p.RENTA_MINIMA <= value <= p.RENTA_MAXIMA


def _importes(frase: str) -> list[_Token]:
    """Amounts in euros, ranges first. Per-m2, yearly and annex amounts are left out."""
    tokens: list[_Token] = []
    taken: list[tuple[int, int]] = []
    for regex in (p.TEXTO_HORQUILLA, p.TEXTO_IMPORTE):
        for match in regex.finditer(frase):
            if any(match.start() < end and start < match.end() for start, end in taken):
                continue
            taken.append(match.span())
            if p.TEXTO_NO_MENSUAL.match(frase[match.end() :]):
                continue
            if regex is p.TEXTO_HORQUILLA:
                low, high = to_number(match["a"]), to_number(match["b"])
                if not (_plausible(low) and _plausible(high) and low < high):
                    continue
            else:
                low, high = to_number(match["n"]), None
                if not _plausible(low):
                    continue
            tokens.append(_Token(match.start(), match.end(), importe=(low, high)))
    return sorted(tokens, key=lambda token: token.inicio)


def _superficie(segment: str) -> float | None:
    found = re.findall(r"(\d{2,3}(?:,\d+)?)\s*m2\s*utiles?\b", segment)
    value = to_number(found[0]) if len(found) == 1 else None
    return value if value is not None and 15 <= value <= 200 else None


def _menciones_de_frase(offset: int, frase: str, parrafo: str) -> list[_Mencion]:
    """Bedrooms and amounts must strictly alternate (D, amount, D, amount...); otherwise nothing."""
    bedrooms = []
    for match in p.TEXTO_DORMITORIOS.finditer(frase):
        if p.TEXTO_LISTA_DORMITORIOS.search(frase[: match.start()]):
            return []
        bedrooms.append(_Token(match.start(), match.end(), dormitorios=int(to_number(match["d"]) or 0)))
    amounts = _importes(frase)
    if not amounts:
        return []
    if bedrooms:
        tokens = sorted(bedrooms + amounts, key=lambda token: token.inicio)
        if [token.importe is None for token in tokens] != [True, False] * len(bedrooms):
            return []
        pairs = [(tokens[i], tokens[i + 1]) for i in range(0, len(tokens), 2)]
    else:
        # Without bedrooms only a range says "these are the rents" (REG-RENTA-03).
        pairs = [(None, token) for token in amounts if token.importe and token.importe[1] is not None]

    mentions = []
    previous_end = 0
    for bedroom, amount in pairs:
        assert amount.importe is not None
        start = bedroom.fin if bedroom else previous_end
        gap = frase[start : amount.inicio]
        before = frase[previous_end : bedroom.inicio] if bedroom else ""
        previous_end = amount.fin
        after = re.split(r"[;,(]", frase[amount.fin : amount.fin + 40])[0]
        if bedroom and len(gap) > 60:
            continue
        if p.TEXTO_AJENO.search(gap) or p.TEXTO_AJENO.search(before) or p.TEXTO_AJENO.search(after):
            continue
        # Without "al mes" the sentence or its paragraph has to speak about rents.
        if not p.TEXTO_MENSUAL.match(frase[amount.fin :]):
            if not p.TEXTO_CONTEXTO_RENTA.search(parrafo) or p.TEXTO_AJENO.search(frase):
                continue
        if not bedroom and not p.TEXTO_CONTEXTO_RENTA.search(frase):
            continue
        low, high = amount.importe
        mentions.append(
            _Mencion(
                dormitorios=bedroom.dormitorios if bedroom else None,
                superficie=_superficie(gap) if bedroom else None,
                renta=low,
                renta_max=high,
                inicio=offset + (bedroom.inicio if bedroom else amount.inicio),
                fin=offset + amount.fin,
            )
        )
    return mentions


def _variantes(mentions: list[_Mencion]) -> list[list[dict]]:
    """The typology list; two different rents for one typology give two different lists."""
    groups: dict[int | None, list[_Mencion]] = {}
    for mention in mentions:
        groups.setdefault(mention.dormitorios, []).append(mention)
    options: list[list[dict]] = []
    for bedrooms, group in groups.items():
        surfaces = sorted({m.superficie for m in group if m.superficie is not None})
        for surface in surfaces or [None]:
            rents: list[tuple[float, float | None]] = []
            for m in group:
                # A mention without surface speaks about every surface of that typology.
                if m.superficie in (surface, None) and (m.renta, m.renta_max) not in rents:
                    rents.append((m.renta, m.renta_max))
            options.append([t.nueva(bedrooms, surface, low, high) for low, high in rents])
    total = max((len(o) for o in options), default=0)
    return [t.ordenar([o[min(i, len(o) - 1)] for o in options]) for i in range(total)]


def _evidencia_m2(doc: Document) -> str | None:
    """REG-RENTA-04: a rent per m2 is only ever quoted, never turned into a monthly rent."""
    for offset, frase in frases(doc):
        match = p.TEXTO_EUR_M2.search(frase)
        if match and p.TEXTO_CONTEXTO_RENTA.search(frase) and "venta" not in frase:
            literal = " ".join(doc.texto[offset + match.start() : offset + match.end()].split())
            return f"REG-RENTA-04: {literal}"
    return None


def _con_m2(result: FieldResult, note: str | None) -> FieldResult:
    if note is None or all(row["superficie_util_m2"] is None for row in result.valor):
        return result
    room = MAX_EVIDENCIA - len(note) - 3
    return replace(result, evidencia=f"{result.evidencia[:room]} | {note}")


class RentasExtractor:
    nombre = "rentas"
    version = "1.0.0"
    campos_soportados = frozenset({CAMPO, CAMPO_OTROS})

    def extract(self, doc: Document, ctx: ExtractionContext) -> list[FieldResult]:
        note = _evidencia_m2(doc)
        results = [_con_m2(result, note) for result in (*self._tablas(doc), *self._texto(doc))]
        return results + self._marcadores(doc)

    def _tablas(self, doc: Document) -> Iterator[FieldResult]:
        # Tables with the same columns that count their dwellings (one per development) add up to
        # one list. Anything else may be an alternative price list: it stays apart and conflicts.
        groups: dict[tuple, list[t.Tabla]] = {}
        for position, table in enumerate(t.tablas_de_renta(doc)):
            additive = table.columnas.num_viviendas is not None
            groups.setdefault(table.clave if additive else (position,), []).append(table)
        for tables in groups.values():
            parts = [table.tipologias() for table in tables]
            # An unreadable table with rows would leave the list silently incomplete.
            if any(not rows and table.filas for table, rows in zip(tables, parts, strict=True)):
                continue
            if rows := t.ordenar([row for part in parts for row in part]):
                continued = any(table.continuada for table in tables)
                confidence = CONFIANZA_TABLA_CONTINUADA if continued else CONFIANZA_TABLA
                yield doc.resultado_tabla(
                    CAMPO, rows, confidence, tables[0].pagina, tables[0].evidencia, "REG-RENTA-01"
                )

    def _texto(self, doc: Document) -> Iterator[FieldResult]:
        mentions: list[_Mencion] = []
        for offset, frase in frases(doc):
            paragraph = doc.parrafo_en(offset)
            assert paragraph is not None
            mentions += _menciones_de_frase(offset, frase, doc.busqueda[paragraph.inicio : paragraph.fin])
        # Quotes of generic legislation only count when nothing else was found.
        own = [m for m in mentions if not doc.parrafo_en(m.inicio).normativo]
        mentions = own or mentions
        # A global range says nothing new once rents per typology are known.
        if any(m.dormitorios is not None for m in mentions):
            mentions = [m for m in mentions if m.dormitorios is not None]
        if not mentions:
            return
        first = mentions[0]
        rule = "REG-RENTA-03" if all(m.renta_max is not None for m in mentions) else "REG-RENTA-02"
        for rows in _variantes(mentions):
            yield doc.resultado(CAMPO, rows, 0.8, first.inicio, first.fin, rule, seccion="rentas")

    def _marcadores(self, doc: Document) -> list[FieldResult]:
        """VAT and community fee statements about the rent, as free-text notes."""
        found: dict[str, FieldResult] = {}
        for offset, frase in frases(doc):
            if not re.search(r"\brentas?\b|alquiler|arrendamiento|mensual|garaje|trastero|/\s*mes\b", frase):
                continue
            if re.search(r"venta|compraventa", frase):
                continue
            for note, rule, regex in p.MARCADORES:
                match = regex.search(frase)
                if match and note not in found:
                    found[note] = doc.resultado(
                        CAMPO_OTROS, note, 0.85, offset + match.start(), offset + match.end(), rule, seccion="rentas"
                    )
        # "incluido" and "no incluido" about different things: neither note is safe on its own.
        for subject in ("IVA", "Gastos de comunidad"):
            both = [note for note in found if note.startswith(subject)]
            if len(both) > 1:
                for note in both:
                    del found[note]
        return list(found.values())
