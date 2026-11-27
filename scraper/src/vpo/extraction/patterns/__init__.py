"""Catalogue of deterministic patterns (ARCHITECTURE.md §5.3), one module per rule family.

All patterns run on ``Document.busqueda``: lowercase, no accents (ñ -> n).
This module holds only what several families share.
"""

from __future__ import annotations

from ...core.normalize import parse_number_es

# Spanish number: "1.234,56", "5,5", "600".
NUM_RE = r"(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)"

NUMBER_WORDS = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}  # fmt: skip
# Longest first, so "una" is not matched as "un".
WORD_RE = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))


def num(group: str = "n") -> str:
    """Named capture group for a Spanish number."""
    return rf"(?P<{group}>{NUM_RE})"


def to_number(text: str) -> float | None:
    """A matched number or number word -> float. Anything else -> None."""
    if text in NUMBER_WORDS:
        return float(NUMBER_WORDS[text])
    return parse_number_es(text)
