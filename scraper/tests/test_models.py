"""The Pydantic models must not drift from the JSON Schema."""

from typing import Literal, get_args, get_origin

import pytest
from conftest import DATA_DIR, build_promo
from pydantic import ValidationError

from vpo.core import models
from vpo.core.jsonio import read_json

DEFS = read_json(DATA_DIR / "schema" / "promocion.schema.json")["$defs"]

PAIRS = {
    "operador": models.Operador,
    "promocion": models.Promocion,
    "documentoBases": models.DocumentoBases,
    "tipologia": models.Tipologia,
    "anejo": models.Anejo,
    "ingresosPorMiembros": models.IngresosPorMiembros,
    "empadronamiento": models.Empadronamiento,
    "edad": models.Edad,
    "requisitos": models.Requisitos,
    "procedencia": models.Procedencia,
    "meta": models.Meta,
}


@pytest.mark.parametrize(("definition", "model"), PAIRS.items())
def test_same_fields_and_all_required(definition, model):
    schema = DEFS[definition]
    assert set(model.model_fields) == set(schema["properties"]) == set(schema["required"])
    assert all(field.is_required() for field in model.model_fields.values())


@pytest.mark.parametrize(
    ("definition", "key"),
    [("regimen", models.Regimen), ("programa", models.Programa), ("estado", models.Estado)],
)
def test_same_enums(definition, key):
    assert get_origin(key) is Literal
    schema_values = DEFS["promocion"]["properties"][definition]["enum"]
    assert set(get_args(key)) == {v for v in schema_values if v is not None}


def test_round_trip():
    promo = build_promo()
    assert models.Promocion.model_validate(promo).model_dump(mode="json") == promo


def test_models_reject_unknown_fields():
    with pytest.raises(ValidationError):
        models.Promocion.model_validate(build_promo() | {"extra": 1})
