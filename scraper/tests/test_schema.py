import pytest
from conftest import DATA_DIR, build_entry, build_field, build_overrides, build_promo, validate_promo

from vpo.core.jsonio import read_json, write_json
from vpo.core.validate import schema_errors, validate_data_dir

SCHEMA_DIR = DATA_DIR / "schema"


def test_repository_data_is_valid():
    assert validate_data_dir(DATA_DIR) == []


def test_synthetic_promotion_is_valid():
    assert validate_promo(build_promo()) == []


def test_missing_key_is_an_error_even_if_nullable():
    promo = build_promo()
    del promo["viviendas_total"]
    assert validate_promo(promo)


def test_unknown_key_is_an_error():
    assert validate_promo(build_promo() | {"extra": 1})


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("fechas", "inscripcion_fin", "31/12/2026"),
        ("enlaces", "oficial", "no es una url"),
        ("ubicacion", "municipio_ine", "08019"),
        ("requisitos", "ingresos_max_iprem", 55),
    ],
)
def test_bad_values_are_rejected(section, key, value):
    promo = build_promo()
    promo[section][key] = value
    assert validate_promo(promo)


def test_bad_timestamp_is_rejected():
    data = {"schema_version": 1, "generado_en": "ayer", "promociones": []}
    assert schema_errors(data, "promociones", SCHEMA_DIR)


@pytest.mark.parametrize("pointer", ["/tipologias/0/renta_mensual_eur", "/meta", "/id", "estado"])
def test_overrides_schema_rejects_bad_pointers(pointer):
    overrides = build_overrides({"demo": build_entry({pointer: build_field(1)})})
    assert schema_errors(overrides, "overrides", SCHEMA_DIR)


def test_iprem_arithmetic_is_checked(data_dir):
    iprem = read_json(data_dir / "iprem.json")
    iprem["valores"][0]["anual_14"] = 1.0
    write_json(data_dir / "iprem.json", iprem)
    assert any("mensual × 14" in e for e in validate_data_dir(data_dir))


def test_overlapping_program_validity_is_rejected(data_dir):
    programas = read_json(data_dir / "programas.json")
    programas["programas"].append(programas["programas"][0] | {"vigente_desde": "2027-01-01"})
    write_json(data_dir / "programas.json", programas)
    assert any("solapadas" in e for e in validate_data_dir(data_dir))


def test_duplicate_key_in_hand_edited_file_is_rejected(data_dir):
    (data_dir / "overrides.json").write_text(
        '{"schema_version": 1, "overrides": {"a": 1, "a": 2}, "promociones_manuales": []}', encoding="utf-8"
    )
    assert any("clave duplicada" in e for e in validate_data_dir(data_dir))


def test_source_file_name_must_match_its_id(data_dir):
    (data_dir / "sources" / "demo.json").rename(data_dir / "sources" / "otra.json")
    assert any("fuente_id" in e for e in validate_data_dir(data_dir))


def test_municipalities():
    municipios = read_json(DATA_DIR / "municipios.json")["municipios"]
    by_code = {m["ine"]: m["nombre"] for m in municipios}
    assert len(by_code) == 179
    assert by_code["28079"] == "Madrid"
