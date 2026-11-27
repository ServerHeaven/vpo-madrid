"""Schema validation of data/ plus the cross-checks JSON Schema cannot express."""

from __future__ import annotations

from datetime import date
from functools import cache
from itertools import combinations
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .jsonio import read_json

DATA_FILES = {
    "promociones.json": "promociones",
    "state.json": "state",
    "overrides.json": "overrides",
    "iprem.json": "iprem",
    "programas.json": "programas",
    "municipios.json": "municipios",
    "fuentes.json": "fuentes",
}


@cache
def _validators(schema_dir: Path) -> dict[str, Draft202012Validator]:
    schemas = {p.name.removesuffix(".schema.json"): read_json(p) for p in schema_dir.glob("*.schema.json")}
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )
    checker = Draft202012Validator.FORMAT_CHECKER
    return {
        name: Draft202012Validator(schema, registry=registry, format_checker=checker)
        for name, schema in schemas.items()
    }


def schema_errors(data: Any, schema_name: str, schema_dir: Path) -> list[str]:
    errors = _validators(schema_dir)[schema_name].iter_errors(data)
    return [f"{e.json_path}: {e.message[:200]}" for e in sorted(errors, key=lambda e: e.json_path)]


def _duplicates(values: list[Any]) -> list[Any]:
    return sorted({v for v in values if values.count(v) > 1})


def _cross_checks(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    iprem = data["iprem.json"]["valores"]
    for row in iprem:
        for field, months in (("anual_12", 12), ("anual_14", 14)):
            if abs(row[field] - row["mensual"] * months) > 0.005:
                errors.append(f"iprem.json: {row['anio']}: {field} no es mensual × {months}")
    errors += [f"iprem.json: año repetido {y}" for y in _duplicates([r["anio"] for r in iprem])]

    entries = data["programas.json"]["programas"]
    for a, b in combinations(entries, 2):
        if a["clave"] != b["clave"]:
            continue
        # null means open-ended on that side.
        start = max(a["vigente_desde"] or date.min.isoformat(), b["vigente_desde"] or date.min.isoformat())
        end = min(a["vigente_hasta"] or date.max.isoformat(), b["vigente_hasta"] or date.max.isoformat())
        if start <= end:
            errors.append(f"programas.json: vigencias solapadas para {a['clave']}")

    codes = [m["ine"] for m in data["municipios.json"]["municipios"]]
    errors += [f"municipios.json: código repetido {c}" for c in _duplicates(codes)]

    sources = [f["id"] for f in data["fuentes.json"]["fuentes"]]
    errors += [f"fuentes.json: id repetido {i}" for i in _duplicates(sources)]

    manual = data["overrides.json"]["promociones_manuales"]
    for label, promos in (("promociones.json", data["promociones.json"]["promociones"]), ("overrides.json", manual)):
        errors += [f"{label}: id repetido {i}" for i in _duplicates([p["id"] for p in promos])]
        for promo in promos:
            if promo["ubicacion"]["municipio_ine"] not in codes:
                errors.append(f"{label}: {promo['id']}: municipio_ine inexistente")
            requisitos = promo["requisitos"]
            errors += [
                f"{label}: {promo['id']}: {name} tiene valor y figura en no_exigidos"
                for name in requisitos["no_exigidos"]
                if requisitos[name] is not None
            ]
    return errors


def source_files(data_dir: Path) -> list[Path]:
    return sorted((data_dir / "sources").glob("*.json"))


def validate_data_dir(data_dir: Path) -> list[str]:
    schema_dir = data_dir / "schema"
    errors: list[str] = []
    data: dict[str, Any] = {}

    files = [(data_dir / name, schema) for name, schema in DATA_FILES.items()]
    files += [(path, "source") for path in source_files(data_dir)]
    for path, schema in files:
        if not path.is_file():
            errors.append(f"{path.name}: no existe")
            continue
        try:
            content = read_json(path)
        except ValueError as error:
            errors.append(str(error))
            continue
        found = schema_errors(content, schema, schema_dir)
        errors += [f"{path.name}: {e}" for e in found]
        if schema == "source" and not found:
            if content["fuente_id"] != path.stem or any(
                p["fuente_id"] != path.stem for p in content["promociones"]
            ):
                errors.append(f"{path.name}: fuente_id no coincide con el nombre del fichero")
        data[path.name] = content

    # Cross-checks assume well-formed files.
    return errors or _cross_checks(data)
