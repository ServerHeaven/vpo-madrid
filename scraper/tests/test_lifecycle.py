import copy
from datetime import date, timedelta

import pytest
from conftest import SCHEMA_DIR, validate_promo
from conftest import build_promo as sample_promo

from vpo.core.jsonio import read_json
from vpo.core.lifecycle import build_promo, mark_missing
from vpo.sources.base import Parsed, procedencia_html

DAY_1 = date(2026, 11, 1)
VANISHED = date(2026, 11, 10)


def parsed(**changes) -> Parsed:
    datos = sample_promo(**changes)
    del datos["id"], datos["meta"]
    return Parsed(datos, {"/estado": procedencia_html("https://example.org/promo", "Plazo abierto")})


def build(data: Parsed, previous: dict | None = None, today: date = DAY_1, version: str = "0.2.0") -> dict:
    return build_promo(
        data, promo_id="demo-madrid-uno", previous=previous, today=today, extractor_version=version
    )


def without_meta(promo: dict) -> dict:
    return {key: value for key, value in promo.items() if key != "meta"}


def test_new_promotion():
    promo = build(parsed())
    assert validate_promo(promo) == []
    assert promo["meta"] == {
        "primera_deteccion": "2026-11-01",
        "ultima_modificacion": "2026-11-01",
        "activa_en_fuente": True,
        "campos_pendientes": [],
        "campos_override": [],
        "procedencia": parsed().procedencia,
        "extractor_version": "0.2.0",
    }


def test_key_order_follows_the_schema():
    schema = read_json(SCHEMA_DIR / "promocion.schema.json")
    data = parsed()
    shuffled = Parsed(dict(reversed(data.datos.items())), data.procedencia)
    assert list(build(shuffled)) == schema["$defs"]["promocion"]["required"]


@pytest.mark.parametrize("change", [{"extra": 1}, {"id": "x"}])
def test_unexpected_keys_are_rejected(change):
    data = parsed()
    with pytest.raises(ValueError):
        build(Parsed(data.datos | change, data.procedencia))


def test_missing_key_is_rejected():
    data = parsed()
    del data.datos["fechas"]
    with pytest.raises(ValueError):
        build(data)


def test_result_does_not_alias_inputs():
    data = parsed()
    original = copy.deepcopy(data)
    promo = build(data)
    promo["ubicacion"]["distrito"] = "Centro"
    promo["meta"]["procedencia"]["/estado"]["confianza"] = 0
    assert data == original


def test_unchanged_data_keeps_modification_date_even_with_new_version():
    first = build(parsed())
    second = build(parsed(), first, DAY_1 + timedelta(days=5), version="0.3.0")
    assert second["meta"]["primera_deteccion"] == "2026-11-01"
    assert second["meta"]["ultima_modificacion"] == "2026-11-01"
    assert second["meta"]["extractor_version"] == "0.3.0"


def test_changed_data_or_provenance_updates_modification_date():
    first = build(parsed())
    later = DAY_1 + timedelta(days=5)
    changed_data = build(parsed(viviendas_total=11), first, later)
    changed_origin = build(Parsed(parsed().datos, {}), first, later)
    for promo in (changed_data, changed_origin):
        assert promo["meta"]["primera_deteccion"] == "2026-11-01"
        assert promo["meta"]["ultima_modificacion"] == "2026-11-06"
        assert validate_promo(promo) == []


def test_first_miss_deactivates_and_records_the_date():
    active = build(parsed())
    original = copy.deepcopy(active)
    missing = mark_missing(active, today=VANISHED)
    assert active == original
    assert missing["meta"]["activa_en_fuente"] is False
    assert missing["meta"]["ultima_modificacion"] == "2026-11-10"
    assert without_meta(missing) == without_meta(active)
    assert validate_promo(missing) == []


@pytest.mark.parametrize(
    ("days", "estado"),
    [(0, "inscripcion_abierta"), (29, "inscripcion_abierta"), (30, "finalizada"), (31, "finalizada")],
)
def test_thirty_day_boundary(days, estado):
    missing = mark_missing(build(parsed()), today=VANISHED)
    original = copy.deepcopy(missing)
    today = VANISHED + timedelta(days=days)
    result = mark_missing(missing, today=today)
    assert missing == original
    assert result is not missing
    assert result["estado"] == estado
    assert result["meta"]["activa_en_fuente"] is False
    assert validate_promo(result) == []
    if estado != "finalizada":
        assert result == original
        return
    assert result["meta"]["ultima_modificacion"] == today.isoformat()
    origin = result["meta"]["procedencia"]["/estado"]
    assert origin["regla"] == "DERIVADA-DESAPARECIDA"
    assert (origin["metodo"], origin["confianza"], origin["pagina"]) == ("html", 1, None)
    assert origin["documento"] == "https://example.org/promo"
    assert "2026-11-10" in origin["evidencia"]


def test_daily_runs_are_idempotent():
    promo = build(parsed())
    history = []
    for offset in range(90):
        promo = mark_missing(promo, today=VANISHED + timedelta(days=offset))
        history.append(promo)
    assert history[0] == history[29]
    assert history[30] == history[89]
    assert history[30]["meta"]["ultima_modificacion"] == "2026-12-10"
    assert mark_missing(history[0], today=VANISHED) == history[0]


def test_already_finished_promotion_is_not_touched_again():
    missing = mark_missing(build(parsed(estado="finalizada")), today=VANISHED)
    assert missing["meta"]["activa_en_fuente"] is False
    assert mark_missing(missing, today=VANISHED + timedelta(days=60)) == missing


@pytest.mark.parametrize("days", [5, 45])
def test_reappearing_promotion_is_active_again(days):
    gone = mark_missing(build(parsed()), today=VANISHED)
    gone = mark_missing(gone, today=VANISHED + timedelta(days=days))
    back_on = VANISHED + timedelta(days=days + 1)
    back = build(parsed(), gone, back_on)
    assert back["estado"] == "inscripcion_abierta"
    assert back["meta"]["activa_en_fuente"] is True
    assert back["meta"]["primera_deteccion"] == "2026-11-01"
    assert back["meta"]["ultima_modificacion"] == back_on.isoformat()
    assert back["meta"]["procedencia"] == parsed().procedencia
    assert validate_promo(back) == []
