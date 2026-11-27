from conftest import build_entry, build_field, build_overrides

from vpo.__main__ import main
from vpo.core.jsonio import read_json, write_json


def cli(command, data_dir, hoy="2026-11-27"):
    return main([command, "--data-dir", str(data_dir), "--hoy", hoy])


def test_merge_then_validate(data_dir):
    assert cli("merge", data_dir) == 0
    output = read_json(data_dir / "promociones.json")
    assert [p["id"] for p in output["promociones"]] == ["demo-madrid-uno"]
    assert output["promociones"][0]["requisitos"]["ingresos_max_iprem"] == 5.5
    assert cli("validate", data_dir) == 0


def test_second_merge_leaves_the_file_untouched(data_dir):
    cli("merge", data_dir)
    first = (data_dir / "promociones.json").read_bytes()
    cli("merge", data_dir, hoy="2026-11-28")
    assert (data_dir / "promociones.json").read_bytes() == first
    assert b"\r\n" not in first


def test_validate_fails_on_a_correction_that_cannot_apply(data_dir):
    entry = build_entry({"/viviendas_total": build_field("muchas")})
    write_json(data_dir / "overrides.json", build_overrides({"demo-madrid-uno": entry}))
    assert cli("validate", data_dir) == 1


def test_validate_fails_on_a_correction_with_unknown_municipality(data_dir):
    entry = build_entry({"/ubicacion/municipio_ine": build_field("28999")})
    write_json(data_dir / "overrides.json", build_overrides({"demo-madrid-uno": entry}))
    assert cli("validate", data_dir) == 1


def test_later_phase_commands_do_not_pretend_to_work(data_dir):
    assert cli("run", data_dir) == 2
