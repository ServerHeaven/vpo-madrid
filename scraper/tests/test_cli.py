import pytest
from conftest import build_entry, build_field, build_overrides

import vpo.__main__ as cli_module
from vpo.__main__ import main
from vpo.core.jsonio import read_json, write_json
from vpo.run import RunReport, SourceReport


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


def deactivate_every_source(data_dir):
    # The copied catalogue is the real one: never let a test reach the web.
    catalogue = read_json(data_dir / "fuentes.json")
    for source in catalogue["fuentes"]:
        source["activa"] = False
    write_json(data_dir / "fuentes.json", catalogue)


@pytest.mark.parametrize("command", ["review", "reparse"])
def test_later_phase_commands_do_not_pretend_to_work(data_dir, command):
    assert cli(command, data_dir) == 2


def test_run_without_active_sources_says_so_and_writes_nothing(data_dir, capsys):
    deactivate_every_source(data_dir)
    state = (data_dir / "state.json").read_bytes()
    assert cli("run", data_dir) == 0
    assert "No hay fuentes activas" in capsys.readouterr().out
    assert (data_dir / "state.json").read_bytes() == state


def test_run_rejects_an_unknown_source(data_dir, capsys):
    deactivate_every_source(data_dir)
    assert main(["run", "--data-dir", str(data_dir), "--fuentes", "no-existe"]) == 2
    assert "no-existe" in capsys.readouterr().err


@pytest.mark.parametrize(("value", "expected"), [("a, b", {"a", "b"}), ("", None), (None, None)])
def test_run_passes_the_requested_sources(data_dir, monkeypatch, value, expected):
    calls = []

    def fake_run(folder, **kwargs):
        calls.append((folder, kwargs))
        return RunReport()

    monkeypatch.setattr(cli_module, "run", fake_run)
    extra = [] if value is None else ["--fuentes", value]
    assert main(["run", "--data-dir", str(data_dir), "--hoy", "2026-11-27", *extra]) == 0
    folder, kwargs = calls[0]
    assert folder == data_dir
    assert kwargs["only"] == expected
    assert kwargs["today"].isoformat() == "2026-11-27"
    assert kwargs["now"].utcoffset() is not None


def test_run_summary_shows_each_source_and_a_failure_does_not_change_the_exit_code(
    data_dir, monkeypatch, capsys
):
    errors = [f"error {n}" for n in range(5)]
    report = RunReport(
        [
            SourceReport("uno", "ok", vistas=4, cambios=1, duracion_s=2.5),
            SourceReport("dos", "error", errores=errors),
        ]
    )
    monkeypatch.setattr(cli_module, "run", lambda folder, **kwargs: report)
    assert cli("run", data_dir) == 0
    out = capsys.readouterr().out
    assert "uno: ok · vistas: 4 · cambios: 1 · 2.5 s" in out
    assert "dos: error · vistas: -" in out
    assert "error 2" in out and "error 3" not in out
    assert "(y 2 más)" in out
