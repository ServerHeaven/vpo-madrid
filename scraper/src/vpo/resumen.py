"""Commit message and job summary of scrape.yml (ARCHITECTURE.md §4.1, steps 10 and 11).

    python -m vpo.resumen mensaje --anterior FILE [--data-dir DIR]
    python -m vpo.resumen tabla   --anterior FILE [--data-dir DIR]

FILE is promociones.json as it was before the run. Read only.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .core.jsonio import read_json

_MAX_ERROR = 200


def _por_id(datos: dict[str, Any] | None) -> dict[str, Any]:
    return {p["id"]: p for p in (datos or {}).get("promociones", [])}


def contar_cambios(anterior: dict[str, Any] | None, actual: dict[str, Any]) -> int:
    """Promotions added, removed or modified."""
    before, after = _por_id(anterior), _por_id(actual)
    return sum(before.get(i) != after.get(i) for i in before.keys() | after.keys())


def contar_pendientes(actual: dict[str, Any]) -> int:
    """Promotions with some key field waiting for review."""
    return sum(bool(p["meta"]["campos_pendientes"]) for p in actual["promociones"])


def mensaje_commit(hoy: date, cambios: int, pendientes: int) -> str:
    return f"data: scrape {hoy.isoformat()} ({cambios} cambios, {pendientes} pendientes)"


def _celda(texto: str) -> str:
    """Error messages quote web pages: keep them inert inside a Markdown table."""
    limpio = " ".join(texto.split())[:_MAX_ERROR]
    for old, new in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ("|", "&#124;"), ("`", "&#96;")):
        limpio = limpio.replace(old, new)
    return f"<code>{limpio}</code>" if limpio else "—"


def tabla(state: dict[str, Any], actual: dict[str, Any], cambios: int) -> str:
    lines = [
        "## Lectura de fuentes",
        "",
        f"- Promociones publicadas: {len(actual['promociones'])}",
        f"- Promociones con cambios: {cambios}",
        f"- Promociones con datos pendientes de revisión: {contar_pendientes(actual)}",
        "",
        "Estado de cada fuente en su última lectura:",
        "",
        "| fuente | estado | vistas | fallos seguidos | última lectura (UTC) | detalle |",
        "|---|---|---|---|---|---|",
    ]
    for source_id, info in sorted(state["fuentes"].items()):
        seen = "—" if info["promociones_vistas"] is None else info["promociones_vistas"]
        lines.append(
            f"| {source_id} | {info['estado']} | {seen} | {info['fallos_consecutivos']} "
            f"| {info['ultima_ejecucion']} | {_celda(info['ultimo_error'] or '')} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vpo.resumen")
    parser.add_argument("command", choices=["mensaje", "tabla"])
    parser.add_argument("--anterior", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args(argv)

    anterior = read_json(args.anterior) if args.anterior.is_file() else None
    actual = read_json(args.data_dir / "promociones.json")
    cambios = contar_cambios(anterior, actual)
    # Error messages may carry any character; the Windows console is not always UTF-8.
    sys.stdout.reconfigure(encoding="utf-8")
    if args.command == "mensaje":
        hoy = datetime.now(ZoneInfo("Europe/Madrid")).date()
        print(mensaje_commit(hoy, cambios, contar_pendientes(actual)))
    else:
        print(tabla(read_json(args.data_dir / "state.json"), actual, cambios), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
