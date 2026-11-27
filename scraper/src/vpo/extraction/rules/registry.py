"""The extractors the pipeline runs. A future LLMExtractor is registered here and nowhere else."""

from __future__ import annotations

from ..base import Extractor
from .anejos import AnejosExtractor
from .edad import EdadExtractor
from .empadronamiento import EmpadronamientoExtractor
from .fechas import FechasExtractor
from .ingresos_iprem import IngresosIpremExtractor
from .rentas import RentasExtractor

EXTRACTORES: tuple[Extractor, ...] = (
    IngresosIpremExtractor(),
    EmpadronamientoExtractor(),
    EdadExtractor(),
    RentasExtractor(),
    AnejosExtractor(),
    FechasExtractor(),
)
