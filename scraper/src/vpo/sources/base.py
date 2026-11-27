"""Contract between source adapters, the HTTP client and the orchestrator.

Adapters only read: they receive a Fetcher and return plain data. They never touch
files, ids, ``meta`` or state.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol

from ..core.normalize import Municipios


class FetchError(Exception):
    """A request could not be completed."""


class RobotsDisallowed(FetchError):
    """robots.txt forbids the URL."""


class HttpStatusError(FetchError):
    def __init__(self, url: str, status: int) -> None:
        super().__init__(f"HTTP {status} en {url}")
        self.url = url
        self.status = status


class DeadlineExceeded(Exception):
    """The source ran out of time. Deliberately not a FetchError: it aborts the whole source."""


class ListingError(Exception):
    """The listing page no longer looks as expected. Aborts the source, keeping the last data."""


@dataclass(frozen=True)
class Response:
    url: str  # final URL after redirects
    requested_url: str
    status: int  # 200, also when served from cache after a 304
    content: bytes
    encoding: str | None
    etag: str | None
    last_modified: str | None
    from_cache: bool = False

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding or "utf-8", errors="replace")


class Fetcher(Protocol):
    def get(self, url: str) -> Response:
        """Return a successful response or raise FetchError / DeadlineExceeded."""
        ...


@dataclass(frozen=True)
class Ficha:
    """One promotion found in a listing.

    ``url`` is its identity: the id is frozen against it, so it must be stable between runs.
    It may carry a fragment when several promotions share one page.
    """

    url: str
    nombre: str
    extra: dict[str, Any] = field(default_factory=dict)  # data already taken from the listing


@dataclass(frozen=True)
class Parsed:
    """``datos`` holds every key of a promotion except ``id`` and ``meta``."""

    datos: dict[str, Any]
    procedencia: dict[str, dict[str, Any]]  # JSON Pointer -> procedencia entry


@dataclass(frozen=True)
class DocumentoRef:
    url: str
    titulo: str
    es_principal: bool


class SourceAdapter(ABC):
    id: ClassVar[str]

    def __init__(self, config: dict[str, Any], municipios: Municipios) -> None:
        self.config = config  # this source's entry in data/fuentes.json
        self.municipios = municipios

    @abstractmethod
    def listar(self, http: Fetcher) -> list[Ficha]:
        """All promotions currently published. Raise ListingError rather than return a partial list."""

    @abstractmethod
    def parsear_ficha(self, ficha: Ficha, http: Fetcher) -> Parsed:
        """Parse one promotion. An exception here only affects this promotion."""

    def documentos(self, ficha: Ficha, http: Fetcher) -> list[DocumentoRef]:
        """Bases documents linked from the promotion. Downloaded and extracted from Phase 3 on."""
        return []

    @abstractmethod
    def selector_hash(self) -> str:
        """CSS selector of the relevant fragment of this source's pages, for change detection."""


# -- builders for the schema's "unknown" shapes ------------------------------------------------


def requisitos_desconocidos() -> dict[str, Any]:
    keys = (
        "ingresos_min_iprem",
        "ingresos_max_iprem",
        "ingresos_por_miembros",
        "iprem_pagas",
        "iprem_ejercicio",
        "tasa_esfuerzo_max",
        "empadronamiento",
        "edad",
        "no_titular_vivienda",
    )
    return dict.fromkeys(keys) | {"otros": []}


def fechas_desconocidas() -> dict[str, Any]:
    return dict.fromkeys(("inscripcion_inicio", "inscripcion_fin", "sorteo", "entrega_prevista"))


def anejo_desconocido() -> dict[str, Any]:
    return {"disponibilidad": "desconocido", "precio_mensual_eur": None}


def tipologia(dormitorios: int | None) -> dict[str, Any]:
    keys = ("superficie_util_m2", "renta_mensual_eur", "renta_mensual_max_eur", "num_viviendas", "adaptada_pmr")
    return dict.fromkeys(keys) | {
        "dormitorios": dormitorios,
        "garaje": anejo_desconocido(),
        "trastero": anejo_desconocido(),
    }


def procedencia_html(
    url: str, evidencia: str | None, *, confianza: float = 0.9, regla: str | None = None
) -> dict[str, Any]:
    return {
        "metodo": "html",
        "confianza": confianza,
        "documento": url,
        "pagina": None,
        "evidencia": evidencia[:400] if evidencia else None,
        "regla": regla,
    }
