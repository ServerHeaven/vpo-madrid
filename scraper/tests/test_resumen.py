from datetime import date

from vpo.core.jsonio import write_json
from vpo.resumen import contar_cambios, contar_pendientes, main, mensaje_commit, tabla


def promo(promo_id, pendientes=(), nombre="A"):
    return {"id": promo_id, "nombre": nombre, "meta": {"campos_pendientes": list(pendientes)}}


def datos(*promos):
    return {"promociones": list(promos)}


def state(error=None, vistas=3):
    return {
        "fuentes": {
            "demo": {
                "estado": "error" if error else "ok",
                "ultima_ejecucion": "2026-11-27T05:00:00Z",
                "fallos_consecutivos": 1 if error else 0,
                "ultimo_error": error,
                "promociones_vistas": vistas,
            }
        }
    }


def test_changes_count_added_removed_and_modified():
    before = datos(promo("igual"), promo("cambia"), promo("se-va"))
    after = datos(promo("igual"), promo("cambia", nombre="B"), promo("nueva"))
    assert contar_cambios(before, after) == 3
    assert contar_cambios(after, after) == 0
    assert contar_cambios(None, after) == 3


def test_pending_counts_promotions_not_fields():
    assert contar_pendientes(datos(promo("a", ["/estado", "/regimen"]), promo("b"))) == 1


def test_commit_message():
    assert mensaje_commit(date(2026, 11, 27), 2, 5) == "data: scrape 2026-11-27 (2 cambios, 5 pendientes)"


def test_table_neutralises_error_text():
    error = "ValueError: <img src=x> | `a`\nsegunda línea"
    text = tabla(state(error, vistas=None), datos(promo("a")), 0)
    row = text.splitlines()[-1]
    assert row.startswith("| demo | error | — | 1 |")
    assert "<img" not in row and "`" not in row
    assert row.count("|") == 7
    assert "segunda línea" in row


def test_cli_reads_the_previous_file(tmp_path, capsys):
    write_json(tmp_path / "promociones.json", datos(promo("a", ["/estado"])))
    write_json(tmp_path / "state.json", state())
    args = ["--data-dir", str(tmp_path), "--anterior", str(tmp_path / "no-existe.json")]
    assert main(["mensaje", *args]) == 0
    assert capsys.readouterr().out.endswith("(1 cambios, 1 pendientes)\n")
    assert main(["tabla", *args]) == 0
    assert "| demo | ok | 3 | 0 |" in capsys.readouterr().out
