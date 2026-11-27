"""Deterministic JSON read/write for versioned data files."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    # Hand-edited files: json would silently keep only the last duplicate, losing a correction.
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"clave duplicada: {key!r}")
        result[key] = value
    return result


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except ValueError as error:
        raise ValueError(f"{path.name}: {error}") from error


def write_json(path: Path, data: Any) -> None:
    """Atomic write with stable formatting (UTF-8, LF, trailing newline)."""
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
