"""Extraction candidates per document, in .cache/extraction/<sha256 of the bytes>-<ine>.json.

Candidates are stored before resolution, so an unchanged document is not extracted again and
the review report can still show what was seen. The cache is disposable: a miss re-extracts.
An entry is valid for the same major.minor of the extractor (ARCHITECTURE.md §3.4 and §5.4).
The municipality is part of the key because some rules depend on it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..core.jsonio import write_json
from .base import FieldResult


@dataclass(frozen=True)
class CacheEntry:
    extractor_version: str
    sha256_texto: str
    municipio_ine: str | None
    necesita_ocr: bool
    candidatos: tuple[FieldResult, ...]
    advertencias: tuple[str, ...] = ()


def same_minor(a: str, b: str) -> bool:
    return a.split(".")[:2] == b.split(".")[:2]


def _path(cache_dir: Path, sha256: str, municipio_ine: str | None) -> Path:
    return cache_dir / "extraction" / f"{sha256}-{municipio_ine or 'x'}.json"


def load(cache_dir: Path, sha256: str, municipio_ine: str | None, version: str) -> CacheEntry | None:
    """None on a miss, an unreadable file or another major.minor version."""
    try:
        data = json.loads(_path(cache_dir, sha256, municipio_ine).read_text(encoding="utf-8"))
        entry = CacheEntry(
            extractor_version=data["extractor_version"],
            sha256_texto=data["sha256_texto"],
            municipio_ine=data["municipio_ine"],
            necesita_ocr=data["necesita_ocr"],
            candidatos=tuple(FieldResult.from_dict(c) for c in data["candidatos"]),
            advertencias=tuple(data["advertencias"]),
        )
        valid = same_minor(entry.extractor_version, version)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return entry if valid else None


def store(cache_dir: Path, sha256: str, entry: CacheEntry) -> None:
    path = _path(cache_dir, sha256, entry.municipio_ine)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        path,
        {
            "extractor_version": entry.extractor_version,
            "sha256_texto": entry.sha256_texto,
            "municipio_ine": entry.municipio_ine,
            "necesita_ocr": entry.necesita_ocr,
            "candidatos": [c.to_dict() for c in entry.candidatos],
            "advertencias": list(entry.advertencias),
        },
    )
