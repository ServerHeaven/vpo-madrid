"""data/state.json: atomic load/save and record keeping.

All functions work on the plain dict that mirrors data/schema/state.schema.json.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .jsonio import read_json, write_json
from .validate import schema_errors

State = dict[str, Any]

_MAPS = ("fuentes", "documentos", "promo_ids")
_KEYS = ("schema_version", "ultima_ejecucion", *_MAPS)
_DEFAULT_PORTS = {"http": "80", "https": "443"}


def empty_state() -> State:
    return {"schema_version": 1, "ultima_ejecucion": None, "fuentes": {}, "documentos": {}, "promo_ids": {}}


def load_state(path: Path) -> State:
    """Missing file -> empty_state(). A corrupt file raises: ids must never be silently lost."""
    if not path.exists():
        return empty_state()
    state = read_json(path)
    # Valid JSON of the wrong shape is just as corrupt as a truncated file.
    if (
        not isinstance(state, dict)
        or set(state) != set(_KEYS)
        or state["schema_version"] != 1
        or not all(isinstance(state[name], dict) for name in _MAPS)
    ):
        raise ValueError(f"{path.name}: no tiene la estructura de un fichero de estado")
    return state


def save_state(path: Path, state: State, schema_dir: Path) -> None:
    """Validate against the schema (ValueError if invalid), then write atomically."""
    errors = schema_errors(state, "state", schema_dir)
    if errors:
        raise ValueError(f"{path.name}: estado no válido: {'; '.join(errors[:5])}")
    # Entries are built with a fixed key order; only the maps depend on insertion order.
    ordered = {key: state[key] for key in _KEYS}
    for name in _MAPS:
        ordered[name] = dict(sorted(state[name].items()))
    write_json(path, ordered)


def canonical_url(url: str) -> str:
    """Lowercase scheme and host, no default port, no fragment."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    userinfo, at, hostport = parts.netloc.rpartition("@")
    host, port = hostport, ""
    head, colon, tail = hostport.rpartition(":")
    # The colons inside a bracketed IPv6 address are not a port separator.
    if colon and "]" not in tail:
        host, port = head, tail
    netloc = userinfo + at + host.lower()
    if port and port != _DEFAULT_PORTS.get(scheme):
        netloc += f":{port}"
    return urlunsplit((scheme, netloc, parts.path, parts.query, ""))


def document_key(url: str) -> str:
    """sha1 hex of canonical_url(url)."""
    return hashlib.sha1(canonical_url(url).encode("utf-8"), usedforsecurity=False).hexdigest()


def record_html_document(
    state: State,
    *,
    url: str,
    fuente_id: str,
    promo_ids: list[str],
    etag: str | None,
    last_modified: str | None,
    sha256_bytes: str | None,
    sha256_texto: str | None,
    today: date,
) -> bool:
    """Insert or update state['documentos']. Return True if new or its text hash changed.

    When the text hash is unchanged only ``ultima_comprobacion`` (and ``promo_ids``) may change:
    byte-level noise in dynamic pages must not produce diffs.

    ``promo_ids`` replaces the stored list: pass every promotion that uses this canonical URL.
    """
    key = document_key(url)
    day = today.isoformat()
    ids = sorted(set(promo_ids))
    previous = state["documentos"].get(key)

    if previous is not None and previous["sha256_texto"] == sha256_texto:
        previous["promo_ids"] = ids
        previous["ultima_comprobacion"] = day
        return False

    state["documentos"][key] = {
        "url": canonical_url(url),
        "tipo": "html",
        "fuente_id": fuente_id,
        "promo_ids": ids,
        "etag": etag,
        "last_modified": last_modified,
        "sha256_bytes": sha256_bytes,
        "sha256_texto": sha256_texto,
        "primera_vez": previous["primera_vez"] if previous else day,
        "ultimo_cambio": day,
        "ultima_comprobacion": day,
        "extractor_version": None,
        "ocr_necesario": False,
    }
    return True


def _utc_timestamp(moment: datetime) -> str:
    if moment.utcoffset() is None:
        raise ValueError("la fecha y hora debe incluir zona horaria")
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_source_run(
    state: State,
    fuente_id: str,
    *,
    estado: str,  # ok | degradado | error
    now: datetime,  # timezone-aware
    promociones_vistas: int | None,
    duracion_s: float,
    error: str | None,
) -> None:
    """Update state['fuentes'][fuente_id] and state['ultima_ejecucion'].

    ok: fallos_consecutivos = 0, ultimo_exito = now.
    degradado: fallos_consecutivos = 0, ultimo_exito unchanged.
    error: fallos_consecutivos += 1, ultimo_exito unchanged.
    """
    if estado not in ("ok", "degradado", "error"):
        raise ValueError(f"estado de fuente desconocido: {estado!r}")
    timestamp = _utc_timestamp(now)
    previous = state["fuentes"].get(fuente_id)
    last_success = previous["ultimo_exito"] if previous else None
    failures = previous["fallos_consecutivos"] if previous else 0

    state["fuentes"][fuente_id] = {
        "estado": estado,
        "ultima_ejecucion": timestamp,
        "ultimo_exito": timestamp if estado == "ok" else last_success,
        "fallos_consecutivos": failures + 1 if estado == "error" else 0,
        "ultimo_error": error,
        "promociones_vistas": promociones_vistas,
        "duracion_s": round(duracion_s, 1),
    }
    state["ultima_ejecucion"] = timestamp
