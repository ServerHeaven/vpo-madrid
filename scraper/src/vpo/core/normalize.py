"""Spanish text, numbers and municipality names -> canonical values."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .jsonio import read_json

_NUMBER_ES = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?")


def fold(text: str) -> str:
    """Lowercase, no accents, single spaces. For comparisons only, never for display."""
    decomposed = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", text))
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(plain.replace("​", "").lower().split())


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(text)).strip("-")


def parse_number_es(text: str) -> float | None:
    """'1.234,56' -> 1234.56. Anything ambiguous or not a number -> None."""
    text = text.strip()
    if not _NUMBER_ES.fullmatch(text):
        return None
    return float(text.replace(".", "").replace(",", "."))


def parse_int_es(text: str) -> int | None:
    number = parse_number_es(text)
    return int(number) if number is not None and number.is_integer() else None


class Municipios:
    """Lookup of the Comunidad de Madrid municipalities by name."""

    def __init__(self, entries: list[dict]) -> None:
        self._by_name: dict[str, tuple[str, str]] = {}
        for entry in entries:
            for name in (entry["nombre"], entry["nombre_ine"]):
                self._by_name[fold(name)] = (entry["ine"], entry["nombre"])

    @classmethod
    def load(cls, data_dir: Path) -> Municipios:
        return cls(read_json(data_dir / "municipios.json")["municipios"])

    def resolve(self, name: str) -> tuple[str, str] | None:
        """(INE code, display name), or None. No fuzzy matching."""
        return self._by_name.get(fold(name))
