"""Contracts of the extraction pipeline (ARCHITECTURE.md §5.1). No IO.

A ``Document`` is built in two steps: ``documents/pdf.py`` fills ``paginas`` and
``preprocess.preparar`` returns a copy with ``texto``, ``busqueda``, ``parrafos`` and
``secciones``. Extractors only read the second form.

``busqueda`` has exactly the same length as ``texto``: rules search the former and quote the
latter with the same offsets.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Protocol

from ..core.normalize import Municipios

SECCIONES = ("requisitos", "rentas", "plazos", "anexo", "otros")
MOTIVOS = ("no_encontrado", "conflicto", "fuera_de_rango", "pdf_escaneado")
MAX_EVIDENCIA = 400
BONUS_SECCION = 0.1
PENALIZACION_NORMATIVA = 0.3
SEPARADOR_PARRAFOS = "\n\n"

# Fields where every accepted candidate adds one string: they can never be in conflict.
CAMPOS_ACUMULATIVOS = frozenset({"/requisitos/otros", "/requisitos/no_exigidos"})
# Pseudo pointers: an annex that applies to every tipologia of the promotion.
CAMPO_GARAJE = "/tipologias/*/garaje"
CAMPO_TRASTERO = "/tipologias/*/trastero"


def _plegar_caracter(char: str) -> str:
    base = "".join(c for c in unicodedata.normalize("NFKD", char) if not unicodedata.combining(c)).lower()
    if len(base) == 1:
        return base
    lower = char.lower()
    return lower if len(lower) == 1 else char


def plegar(texto: str) -> str:
    """Lowercase without accents (ñ -> n), one output character per input character."""
    return "".join(map(_plegar_caracter, texto))


@dataclass(frozen=True)
class Block:
    bbox: tuple[float, float, float, float]
    texto: str


Table = tuple[tuple[str, ...], ...]  # rows of cells; an empty cell is ""


@dataclass(frozen=True)
class Page:
    numero: int  # 1-based
    texto: str
    bloques: tuple[Block, ...] = ()
    tablas: tuple[Table, ...] = ()


@dataclass(frozen=True)
class Paragraph:
    inicio: int  # offsets into Document.texto
    fin: int
    pagina: int
    seccion: str  # one of SECCIONES
    normativo: bool  # quotes generic legislation: lower confidence


@dataclass(frozen=True)
class Section:
    pag_ini: int
    pag_fin: int
    texto: str


@dataclass(frozen=True)
class FieldResult:
    campo: str  # JSON Pointer of the promotion, or CAMPO_GARAJE / CAMPO_TRASTERO
    valor: Any  # JSON-serialisable, shaped as promocion.schema.json
    confianza: float
    pagina: int | None
    evidencia: str  # <= 400 characters
    regla: str  # pattern id, e.g. "REG-IPREM-01"
    metodo: str  # "pdf_texto" | "pdf_tabla" | "html" | "llm"
    documento: str | None = None  # url of the document it came from

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FieldResult:
        return cls(**data)


@dataclass(frozen=True)
class Descarte:
    """A field left null although something was seen (or the document could not be read)."""

    campo: str
    motivo: str  # one of MOTIVOS
    candidatos: tuple[FieldResult, ...] = ()


@dataclass(frozen=True)
class ExtractionResult:
    campos: tuple[FieldResult, ...] = ()  # accepted: at most one per field (accumulative: one per value)
    descartes: tuple[Descarte, ...] = ()
    advertencias: tuple[str, ...] = ()
    necesita_ocr: bool = False

    def valor(self, campo: str) -> Any:
        return next((r.valor for r in self.campos if r.campo == campo), None)


@dataclass(frozen=True)
class Document:
    url: str
    tipo: str  # "pdf" | "html"
    sha256: str  # of the raw bytes
    paginas: tuple[Page, ...]
    necesita_ocr: bool = False
    texto: str = ""  # cleaned original text; paragraphs joined by SEPARADOR_PARRAFOS
    busqueda: str = ""  # plegar(texto)
    parrafos: tuple[Paragraph, ...] = ()
    secciones: dict[str, Section] = field(default_factory=dict)

    # -- helpers for rules ------------------------------------------------------------------

    def parrafo_en(self, pos: int) -> Paragraph | None:
        """The paragraph holding offset ``pos`` (or the last one starting before it)."""
        found = None
        for paragraph in self.parrafos:
            if paragraph.inicio > pos:
                break
            found = paragraph
        return found

    def pagina_en(self, pos: int) -> int | None:
        paragraph = self.parrafo_en(pos)
        return paragraph.pagina if paragraph else None

    def confianza(self, base: float, pos: int, seccion: str | None = None) -> float:
        """``base`` +0.1 inside the preferred section, -0.3 in a normative paragraph."""
        paragraph = self.parrafo_en(pos)
        if paragraph is None:
            return round(base, 2)
        value = base
        if seccion is not None and paragraph.seccion == seccion:
            value += BONUS_SECCION
        if paragraph.normativo:
            value -= PENALIZACION_NORMATIVA
        return round(min(max(value, 0.0), 1.0), 2)

    def evidencia(self, inicio: int, fin: int) -> str:
        """Literal text around texto[inicio:fin], one line, at most MAX_EVIDENCIA characters."""
        paragraph = self.parrafo_en(inicio)
        low = paragraph.inicio if paragraph else 0
        end_paragraph = self.parrafo_en(max(fin - 1, inicio))
        high = end_paragraph.fin if end_paragraph else len(self.texto)
        if high - low > MAX_EVIDENCIA:
            margin = max(MAX_EVIDENCIA - (fin - inicio), 0) // 2
            low = max(low, inicio - margin)
            high = min(high, low + MAX_EVIDENCIA)
        return " ".join(self.texto[low:high].split())[:MAX_EVIDENCIA]

    def resultado(
        self,
        campo: str,
        valor: Any,
        base: float,
        inicio: int,
        fin: int,
        regla: str,
        *,
        seccion: str | None = None,
    ) -> FieldResult:
        """A text candidate found at texto[inicio:fin]."""
        return FieldResult(
            campo=campo,
            valor=valor,
            confianza=self.confianza(base, inicio, seccion),
            pagina=self.pagina_en(inicio),
            evidencia=self.evidencia(inicio, fin),
            regla=regla,
            metodo="pdf_texto",
            documento=self.url,
        )

    def resultado_tabla(
        self, campo: str, valor: Any, confianza: float, pagina: int, evidencia: str, regla: str
    ) -> FieldResult:
        """A candidate read from Page.tablas."""
        return FieldResult(
            campo=campo,
            valor=valor,
            confianza=confianza,
            pagina=pagina,
            evidencia=" ".join(evidencia.split())[:MAX_EVIDENCIA],
            regla=regla,
            metodo="pdf_tabla",
            documento=self.url,
        )

    @classmethod
    def desde_parrafos(
        cls,
        paginas: Sequence[Sequence[str]],
        *,
        url: str = "https://example.org/bases.pdf",
        seccion: str = "otros",
        normativo: bool = False,
        tablas: dict[int, Iterable[Table]] | None = None,
    ) -> Document:
        """A prepared document built by hand, without preprocessing. Meant for rule tests.

        ``paginas`` is one list of paragraphs per page; ``tablas`` maps page number to tables.
        Every paragraph gets the same ``seccion`` and ``normativo`` flag.
        """
        pages: list[Page] = []
        paragraphs: list[Paragraph] = []
        pieces: list[str] = []
        offset = 0
        for number, texts in enumerate(paginas, 1):
            clean = [" ".join(text.split()) for text in texts]
            pages.append(Page(number, SEPARADOR_PARRAFOS.join(clean), tablas=tuple((tablas or {}).get(number, ()))))
            for text in clean:
                paragraphs.append(Paragraph(offset, offset + len(text), number, seccion, normativo))
                pieces.append(text)
                offset += len(text) + len(SEPARADOR_PARRAFOS)
        full = SEPARADOR_PARRAFOS.join(pieces)
        return cls(
            url=url,
            tipo="pdf",
            sha256="0" * 64,
            paginas=tuple(pages),
            texto=full,
            busqueda=plegar(full),
            parrafos=tuple(paragraphs),
        )


@dataclass(frozen=True)
class ExtractionContext:
    fuente_id: str
    fecha_ref: date
    municipios: Municipios
    municipio_ine: str | None = None  # of the promotion
    programa_hint: str | None = None
    promo_parcial: dict[str, Any] | None = None  # what the HTML already gave


class Extractor(Protocol):
    nombre: str
    version: str
    campos_soportados: frozenset[str]

    def extract(self, doc: Document, ctx: ExtractionContext) -> list[FieldResult]:
        """Every candidate found. No deduplication or conflict handling: that is the pipeline's job."""
        ...
