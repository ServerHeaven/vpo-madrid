import copy
from datetime import date

import pytest
from conftest import (
    SHA_B,
    build_entry,
    build_field,
    build_overrides,
    build_promo,
    validate_promo,
)

from vpo.core.merge import DERIVED_STATE_RULE, merge

TODAY = date(2026, 11, 27)
PROMO_ID = "demo-madrid-uno"


def run(promos, overrides=None, today=TODAY):
    return merge(promos, overrides or build_overrides(), today=today, validate=validate_promo)


def corrected(campos, promo=None):
    return run([promo or build_promo()], build_overrides({PROMO_ID: build_entry(campos)}))


def kinds(result):
    return [a.tipo for a in result.avisos]


def test_without_overrides_returns_scraped_data_sorted_by_id():
    result = run([build_promo("demo-b"), build_promo("demo-a")])
    assert [p["id"] for p in result.promociones] == ["demo-a", "demo-b"]
    assert result.avisos == []


def test_override_wins_and_is_traced():
    result = corrected({"/requisitos/ingresos_max_iprem": build_field(5.5)})
    promo = result.promociones[0]
    assert promo["requisitos"]["ingresos_max_iprem"] == 5.5
    assert promo["meta"]["campos_override"] == ["/requisitos/ingresos_max_iprem"]
    assert promo["meta"]["campos_pendientes"] == []
    assert promo["meta"]["ultima_modificacion"] == "2026-11-20"
    assert promo["meta"]["procedencia"]["/requisitos/ingresos_max_iprem"]["metodo"] == "override"
    assert result.avisos == []
    assert validate_promo(promo) == []


def test_inputs_are_not_mutated():
    promo, overrides = build_promo(), build_overrides(
        {PROMO_ID: build_entry({"/viviendas_total": build_field(20)})}
    )
    before = copy.deepcopy((promo, overrides))
    run([promo], overrides)
    assert (promo, overrides) == before


def test_whole_array_replacement_resolves_pending_children():
    promo = build_promo()
    promo["meta"]["campos_pendientes"] = ["/tipologias/0/renta_mensual_eur"]
    rows = [dict(promo["tipologias"][0], renta_mensual_eur=512.0)]
    result = corrected({"/tipologias": build_field(rows)}, promo)
    assert result.promociones[0]["tipologias"] == rows
    assert result.promociones[0]["meta"]["campos_pendientes"] == []


@pytest.mark.parametrize("pointer", ["/tipologias/0/renta_mensual_eur", "/meta/activa_en_fuente", "/id"])
def test_forbidden_pointers_are_rejected(pointer):
    result = corrected({pointer: build_field(1)})
    assert kinds(result) == ["override_invalido"]
    assert result.promociones == [build_promo()]


def test_invalid_value_is_skipped_but_other_corrections_apply():
    result = corrected(
        {"/viviendas_total": build_field("muchas"), "/requisitos/ingresos_max_iprem": build_field(7.5)}
    )
    promo = result.promociones[0]
    assert kinds(result) == ["override_invalido"]
    assert promo["viviendas_total"] == 10
    assert promo["requisitos"]["ingresos_max_iprem"] == 7.5


def test_cannot_create_a_field_inside_a_null_object():
    result = corrected({"/requisitos/empadronamiento/anios_min": build_field(3)})
    assert kinds(result) == ["override_invalido"]
    assert result.promociones[0]["requisitos"]["empadronamiento"] is None


def test_unknown_key_is_rejected():
    assert kinds(corrected({"/requisitos/inventado": build_field(1)})) == ["override_invalido"]


def test_more_specific_pointer_wins_over_whole_object():
    requisitos = build_promo()["requisitos"] | {"ingresos_max_iprem": 7.5}
    result = corrected(
        {"/requisitos/ingresos_max_iprem": build_field(5.5), "/requisitos": build_field(requisitos)}
    )
    assert result.promociones[0]["requisitos"]["ingresos_max_iprem"] == 5.5


def test_hidden_promotion_is_removed_without_orphan_warning():
    result = run([build_promo()], build_overrides({PROMO_ID: build_entry(ocultar=True)}))
    assert result.promociones == []
    assert result.avisos == []


def test_orphan_override_warns():
    result = run([build_promo()], build_overrides({"no-existe": build_entry()}))
    assert kinds(result) == ["override_huerfano"]
    assert len(result.promociones) == 1


def test_stale_override_still_applies_and_warns():
    result = corrected({"/requisitos/ingresos_max_iprem": build_field(5.5, sha=SHA_B)})
    assert kinds(result) == ["override_desfasado"]
    assert result.promociones[0]["requisitos"]["ingresos_max_iprem"] == 5.5


def test_override_without_hash_is_never_stale():
    assert corrected({"/viviendas_total": build_field(20, sha=None)}).avisos == []


def test_manual_promotion_is_included_and_beats_scraped_duplicate():
    manual = build_promo(fuente_id="manual", viviendas_total=99)
    result = run([build_promo()], build_overrides(manual=[manual]))
    assert [p["viviendas_total"] for p in result.promociones] == [99]
    assert kinds(result) == ["id_duplicado"]


def test_expired_deadline_closes_registration_deterministically():
    first = run([build_promo()], today=date(2026, 12, 16)).promociones[0]
    later = run([build_promo()], today=date(2027, 3, 1)).promociones[0]
    assert first["estado"] == "inscripcion_cerrada"
    assert first["meta"]["procedencia"]["/estado"]["regla"] == DERIVED_STATE_RULE
    assert first == later
    assert validate_promo(first) == []


def test_registration_stays_open_on_the_deadline_day():
    result = run([build_promo()], today=date(2026, 12, 15))
    assert result.promociones[0]["estado"] == "inscripcion_abierta"


def test_manual_state_beats_derived_state():
    overrides = build_overrides({PROMO_ID: build_entry({"/estado": build_field("inscripcion_abierta")})})
    result = run([build_promo()], overrides, today=date(2027, 1, 1))
    assert result.promociones[0]["estado"] == "inscripcion_abierta"


def test_corrected_deadline_drives_derived_state():
    overrides = build_overrides(
        {PROMO_ID: build_entry({"/fechas/inscripcion_fin": build_field("2027-01-31")})}
    )
    result = run([build_promo()], overrides, today=date(2027, 1, 1))
    assert result.promociones[0]["estado"] == "inscripcion_abierta"


def test_correction_fills_an_unknown_modalidad():
    result = corrected({"/modalidad": build_field("alquiler_opcion_compra")}, build_promo(modalidad=None))
    assert result.promociones[0]["modalidad"] == "alquiler_opcion_compra"
    assert result.avisos == []

