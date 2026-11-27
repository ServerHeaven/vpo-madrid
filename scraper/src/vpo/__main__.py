"""CLI: python -m vpo run|merge|validate|review|reparse"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .core.jsonio import read_json, write_json
from .core.merge import MergeResult, merge
from .core.validate import schema_errors, source_files, validate_data_dir

NOT_YET = {"run": 2, "review": 3, "reparse": 3}  # command -> phase that implements it


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vpo")
    parser.add_argument("command", choices=["run", "merge", "validate", "review", "reparse"])
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--hoy", type=date.fromisoformat, help="fecha de referencia (AAAA-MM-DD)")
    args = parser.parse_args(argv)

    if args.command in NOT_YET:
        print(f"'{args.command}' se implementa en la Fase {NOT_YET[args.command]}", file=sys.stderr)
        return 2

    data_dir = args.data_dir or find_data_dir(Path.cwd())
    today = args.hoy or datetime.now(ZoneInfo("Europe/Madrid")).date()
    handler = cmd_merge if args.command == "merge" else cmd_validate
    return handler(data_dir, today)


if __name__ == "__main__":
    sys.exit(main())
