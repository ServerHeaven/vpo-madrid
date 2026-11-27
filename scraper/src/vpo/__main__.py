"""CLI: python -m vpo run|reparse|merge|validate|review [report|sync-issues|health|heartbeat]"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import __version__
from .core.jsonio import read_json, write_json
from .core.merge import MergeResult, merge
from .core.normalize import Municipios
from .core.validate import schema_errors, source_files, validate_data_dir
from .review.issues import GhClient, sync_health, sync_heartbeat, sync_issues
from .review.report import construir_informe, escribir_informe
from .run import SourceReport, UnknownSourceError, run

REPOSITORY = "ServerHeaven/vpo-madrid"
REPORT_NAME = "review-report.json"  # ephemeral, ignored by git
SHOWN_ERRORS = 3  # per source in the run summary


def find_data_dir(start: Path) -> Path:
    for folder in (start, *start.parents):
        if (folder / "data" / "schema").is_dir():
            return folder / "data"
    raise SystemExit("No encuentro data/schema; usa --data-dir")


def run_merge(data_dir: Path, today: date) -> MergeResult:
    """Merge from disk without writing. Raises SystemExit if an input is invalid."""
    schema_dir = data_dir / "schema"
    inputs = [(data_dir / "overrides.json", "overrides")]
    inputs += [(path, "source") for path in source_files(data_dir)]
    loaded = []
    for path, schema in inputs:
        content = read_json(path)
        if errors := schema_errors(content, schema, schema_dir):
            raise SystemExit(f"{path.name} no cumple el schema:\n  " + "\n  ".join(errors[:20]))
        loaded.append(content)

    overrides, *sources = loaded
    return merge(
        (promo for source in sources for promo in source["promociones"]),
        overrides,
        today=today,
        validate=lambda promo: schema_errors(promo, "promocion", schema_dir),
    )


def cmd_merge(data_dir: Path, today: date) -> int:
    result = run_merge(data_dir, today)
    for aviso in result.avisos:
        print(f"AVISO {aviso.tipo} [{aviso.promo_id}] {aviso.detalle}", file=sys.stderr)

    target = data_dir / "promociones.json"
    if target.is_file() and read_json(target).get("promociones") == result.promociones:
        print(f"Sin cambios ({len(result.promociones)} promociones)")
        return 0

    output = {
        "schema_version": 1,
        "generado_en": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "promociones": result.promociones,
    }
    if errors := schema_errors(output, "promociones", data_dir / "schema"):
        raise SystemExit("El resultado de la fusión no cumple el schema:\n  " + "\n  ".join(errors[:20]))
    write_json(target, output)
    print(f"Escritas {len(result.promociones)} promociones en {target.name}")
    return 0


def cmd_validate(data_dir: Path, today: date) -> int:
    errors = validate_data_dir(data_dir)
    if not errors:
        # Dry run of the merge: a correction that cannot be applied must fail the PR.
        result = run_merge(data_dir, today)
        for aviso in result.avisos:
            line = f"{aviso.tipo} [{aviso.promo_id}] {aviso.detalle}"
            if aviso.tipo == "override_invalido":
                errors.append(f"overrides.json: {line}")
            else:
                print(f"AVISO {line}", file=sys.stderr)
        codes = {m["ine"] for m in read_json(data_dir / "municipios.json")["municipios"]}
        errors += [
            f"fusión: {p['id']}: municipio_ine inexistente"
            for p in result.promociones
            if p["ubicacion"]["municipio_ine"] not in codes
        ]
    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)
    print(f"{len(errors)} errores" if errors else "data/ es válido")
    return 1 if errors else 0


def _summary(report: SourceReport) -> list[str]:
    seen = "-" if report.vistas is None else report.vistas
    lines = [
        f"{report.fuente_id}: {report.estado} · vistas: {seen} · cambios: {report.cambios}"
        f" · {report.duracion_s:.1f} s"
    ]
    lines += [f"  {error}" for error in report.errores[:SHOWN_ERRORS]]
    if len(report.errores) > SHOWN_ERRORS:
        lines.append(f"  (y {len(report.errores) - SHOWN_ERRORS} más)")
    return lines


def cmd_run(data_dir: Path, today: date, only: set[str] | None, force_reparse: bool = False) -> int:
    """Exit 0 even if sources fail: only a global problem makes the command fail."""
    try:
        result = run(
            data_dir, today=today, now=datetime.now(UTC), only=only, force_reparse=force_reparse
        )
    except UnknownSourceError as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 2
    if not result.fuentes:
        print("No hay fuentes activas en fuentes.json")
    for report in result.fuentes:
        print("\n".join(_summary(report)))
    return 0


def build_report(data_dir: Path, today: date) -> dict:
    result = run_merge(data_dir, today)
    report = construir_informe(
        result.promociones,
        result.avisos,
        overrides=read_json(data_dir / "overrides.json"),
        cache_dir=data_dir.resolve().parent / ".cache",
        municipios=Municipios.load(data_dir),
        today=today,
        version=__version__,
    )
    escribir_informe(data_dir / REPORT_NAME, report)
    return report


def cmd_review(data_dir: Path, today: date, action: str) -> int:
    """report only writes the file; the other actions talk to GitHub through `gh`."""
    if action == "report":
        build_report(data_dir, today)
        print(f"Informe escrito en {data_dir / REPORT_NAME}")
        return 0

    gh = GhClient(os.environ.get("GITHUB_REPOSITORY") or REPOSITORY)
    if action == "sync-issues":
        summary = sync_issues(build_report(data_dir, today), gh)
    else:
        check = sync_health if action == "health" else sync_heartbeat
        summary = check(read_json(data_dir / "state.json"), gh, now=datetime.now(UTC))
    print(summary)
    return 1 if summary.errores else 0


def _source_ids(value: str) -> set[str] | None:
    # An empty value means "all", so a workflow can always pass the option.
    return {part.strip() for part in value.split(",") if part.strip()} or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vpo")
    parser.add_argument("command", choices=["run", "merge", "validate", "review", "reparse"])
    parser.add_argument(
        "action", nargs="?", choices=["report", "sync-issues", "health", "heartbeat"], help="review: qué hacer"
    )
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--hoy", type=date.fromisoformat, help="fecha de referencia (AAAA-MM-DD)")
    parser.add_argument("--fuentes", type=_source_ids, help="run: ids separados por coma (vacío = todas)")
    parser.add_argument("--forzar-reparse", action="store_true", help="run: vuelve a extraer todos los PDF")
    args = parser.parse_args(argv)

    if (args.command == "review") != (args.action is not None):
        parser.error("'review' necesita una acción (report, sync-issues, health o heartbeat) y las demás órdenes ninguna")

    data_dir = args.data_dir or find_data_dir(Path.cwd())
    today = args.hoy or datetime.now(ZoneInfo("Europe/Madrid")).date()
    if args.command in ("run", "reparse"):
        # reparse is a run that extracts every PDF again, whatever the cache says.
        return cmd_run(data_dir, today, args.fuentes, args.forzar_reparse or args.command == "reparse")
    if args.command == "review":
        return cmd_review(data_dir, today, args.action)
    handler = cmd_merge if args.command == "merge" else cmd_validate
    return handler(data_dir, today)


if __name__ == "__main__":
    sys.exit(main())
