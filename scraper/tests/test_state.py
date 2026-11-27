import copy
import hashlib
from datetime import date, datetime, timedelta, timezone

import pytest
from conftest import DATA_DIR, SCHEMA_DIR, SHA_A, SHA_B

from vpo.core.jsonio import read_json
from vpo.core.state import (
    canonical_url,
    document_key,
    empty_state,
    load_state,
    record_html_document,
    record_source_run,
    save_state,
)
from vpo.core.validate import schema_errors

DAY_1 = date(2026, 11, 1)
DAY_2 = date(2026, 11, 2)
NOW = datetime(2026, 11, 1, 5, 20, 10, 987654, tzinfo=timezone.utc)
URL = "https://example.org/promo"


def errors(state: dict) -> list[str]:
    return schema_errors(state, "state", SCHEMA_DIR)


def record(state: dict, **changes) -> bool:
    arguments = {
        "url": URL,
        "fuente_id": "demo",
        "promo_ids": ["demo-madrid-uno"],
        "etag": '"v1"',
        "last_modified": None,
        "sha256_bytes": SHA_A,
        "sha256_texto": SHA_A,
        "today": DAY_1,
    }
    return record_html_document(state, **(arguments | changes))


def run_source(state: dict, estado: str, now: datetime = NOW, **changes) -> None:
    arguments = {"promociones_vistas": 3, "duracion_s": 1.5, "error": None}
    record_source_run(state, "demo", estado=estado, now=now, **(arguments | changes))


def test_empty_state_matches_versioned_file_shape():
    state = empty_state()
    assert errors(state) == []
    assert list(state) == list(read_json(DATA_DIR / "state.json"))
    state["promo_ids"]["x"] = "x"
    assert empty_state()["promo_ids"] == {}


def test_missing_file_gives_empty_state(tmp_path):
    assert load_state(tmp_path / "state.json") == empty_state()


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b'{"schema_version": 1, ',
        b"\xff\xfe",
        b"[]",
        b"{}",
        b'{"schema_version": 2, "ultima_ejecucion": null, "fuentes": {}, "documentos": {}, "promo_ids": {}}',
        b'{"schema_version": 1, "ultima_ejecucion": null, "fuentes": {}, "documentos": {}, "promo_ids": []}',
        b'{"schema_version": 1, "ultima_ejecucion": null, "fuentes": {}, "documentos": {},'
        b' "promo_ids": {"u": "a", "u": "b"}}',
    ],
)
def test_corrupt_file_raises(tmp_path, content):
    path = tmp_path / "state.json"
    path.write_bytes(content)
    with pytest.raises(ValueError):
        load_state(path)


def test_save_and_load_is_deterministic(tmp_path):
    first, second = empty_state(), empty_state()
    first["promo_ids"] = {"https://b": "b", "https://a": "a"}
    second["promo_ids"] = {"https://a": "a", "https://b": "b"}
    record(first, url="https://example.org/1")
    record(first, url="https://example.org/2")
    record(second, url="https://example.org/2")
    record(second, url="https://example.org/1")
    original = copy.deepcopy(first)

    save_state(tmp_path / "first.json", first, SCHEMA_DIR)
    save_state(tmp_path / "second.json", second, SCHEMA_DIR)

    assert (tmp_path / "first.json").read_bytes() == (tmp_path / "second.json").read_bytes()
    assert load_state(tmp_path / "first.json") == original
    assert list(load_state(tmp_path / "first.json")["promo_ids"]) == ["https://a", "https://b"]
    assert first == original


def test_invalid_state_is_not_written(tmp_path):
    path = tmp_path / "state.json"
    save_state(path, empty_state(), SCHEMA_DIR)
    before = path.read_bytes()
    bad = empty_state()
    bad["promo_ids"]["u"] = "Not A Slug"
    with pytest.raises(ValueError):
        save_state(path, bad, SCHEMA_DIR)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("HTTPS://Example.ORG/Ruta?B=1#frag", "https://example.org/Ruta?B=1"),
        ("https://example.org:443/a", "https://example.org/a"),
        ("http://example.org:80/a", "http://example.org/a"),
        ("http://example.org:443/a", "http://example.org:443/a"),
        ("https://example.org:8443/a", "https://example.org:8443/a"),
        ("https://User:Pw@Example.org/a", "https://User:Pw@example.org/a"),
        ("https://[2001:DB8::1]:443/a", "https://[2001:db8::1]/a"),
        ("https://[2001:DB8::1]/a", "https://[2001:db8::1]/a"),
    ],
)
def test_canonical_url(url, expected):
    assert canonical_url(url) == expected
    assert canonical_url(expected) == expected


def test_document_key_is_sha1_of_canonical_url():
    assert document_key("HTTPS://EXAMPLE.org:443/promo#x") == hashlib.sha1(URL.encode()).hexdigest()


def test_new_document():
    state = empty_state()
    assert record(state, url=URL + "#a", promo_ids=["b", "a", "b"]) is True
    entry = state["documentos"][document_key(URL)]
    assert entry["url"] == URL
    assert entry["tipo"] == "html"
    assert entry["promo_ids"] == ["a", "b"]
    assert entry["primera_vez"] == entry["ultimo_cambio"] == entry["ultima_comprobacion"] == "2026-11-01"
    assert entry["extractor_version"] is None
    assert entry["ocr_necesario"] is False
    assert errors(state) == []


def test_unchanged_text_only_touches_check_date_and_ids():
    state = empty_state()
    record(state)
    before = copy.deepcopy(state["documentos"][document_key(URL)])
    changed = record(
        state,
        today=DAY_2,
        etag='"v2"',
        last_modified="Mon, 02 Nov 2026 10:00:00 GMT",
        sha256_bytes=SHA_B,
        fuente_id="otra",
        promo_ids=["z"],
    )
    assert changed is False
    expected = before | {"ultima_comprobacion": "2026-11-02", "promo_ids": ["z"]}
    assert state["documentos"][document_key(URL)] == expected


def test_changed_text_updates_everything_but_first_seen():
    state = empty_state()
    record(state)
    assert record(state, today=DAY_2, etag='"v2"', sha256_bytes=SHA_B, sha256_texto=SHA_B) is True
    entry = state["documentos"][document_key(URL)]
    assert (entry["etag"], entry["sha256_bytes"], entry["sha256_texto"]) == ('"v2"', SHA_B, SHA_B)
    assert entry["primera_vez"] == "2026-11-01"
    assert entry["ultimo_cambio"] == entry["ultima_comprobacion"] == "2026-11-02"
    assert errors(state) == []


def test_source_run_counters():
    state = empty_state()
    run_source(state, "error", error="HTTP 500", promociones_vistas=None)
    assert state["fuentes"]["demo"]["ultimo_exito"] is None
    assert state["fuentes"]["demo"]["fallos_consecutivos"] == 1
    assert errors(state) == []

    run_source(state, "ok")
    assert state["fuentes"]["demo"]["ultimo_exito"] == "2026-11-01T05:20:10Z"
    assert state["fuentes"]["demo"]["fallos_consecutivos"] == 0

    later = NOW + timedelta(days=1)
    run_source(state, "error", later, error="x")
    run_source(state, "error", later, error="x")
    assert state["fuentes"]["demo"]["fallos_consecutivos"] == 2
    assert state["fuentes"]["demo"]["ultimo_exito"] == "2026-11-01T05:20:10Z"

    run_source(state, "degradado", later)
    entry = state["fuentes"]["demo"]
    assert entry["fallos_consecutivos"] == 0
    assert entry["ultimo_exito"] == "2026-11-01T05:20:10Z"
    assert entry["ultima_ejecucion"] == state["ultima_ejecucion"] == "2026-11-02T05:20:10Z"
    assert errors(state) == []


def test_source_run_converts_to_utc():
    state = empty_state()
    run_source(state, "ok", datetime(2026, 11, 1, 6, 0, tzinfo=timezone(timedelta(hours=1))))
    assert state["ultima_ejecucion"] == "2026-11-01T05:00:00Z"


def test_source_run_rejects_naive_time_and_unknown_status():
    with pytest.raises(ValueError):
        run_source(empty_state(), "ok", datetime(2026, 11, 1, 6, 0))
    with pytest.raises(ValueError):
        run_source(empty_state(), "bien")
