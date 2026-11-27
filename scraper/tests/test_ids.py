import re

import pytest
from conftest import SCHEMA_DIR

from vpo.core.ids import build_slug, get_or_create_id
from vpo.core.state import empty_state
from vpo.core.validate import schema_errors

SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def get(state: dict, url: str, nombre: str = "Vallecas Ensanche 34", municipio: str = "Madrid") -> str:
    return get_or_create_id(state, url=url, operador_id="emvs-madrid", municipio=municipio, nombre=nombre)


def test_slug_from_the_three_parts():
    slug = build_slug("emvs-madrid", "Madrid", "Vallecas Ensanche 34")
    assert slug == "emvs-madrid-madrid-vallecas-ensanche-34"
    slug = build_slug("demo", "Alcalá de Henares", "  La Niña (fase II) ")
    assert slug == "demo-alcala-de-henares-la-nina-fase-ii"


def test_empty_parts_do_not_double_hyphens():
    assert build_slug("demo", "Madrid", "***") == "demo-madrid"
    with pytest.raises(ValueError):
        build_slug("", "", "***")


@pytest.mark.parametrize("length", range(100, 125))
def test_slug_is_truncated_without_trailing_hyphen(length):
    slug = build_slug("demo", "Madrid", "a" * length + " bb cc dd")
    assert len(slug) <= 120
    assert SLUG.fullmatch(slug)


def test_id_is_frozen_per_url():
    state = empty_state()
    first = get(state, "https://example.org/a")
    assert get(state, "https://example.org/a", nombre="Otro nombre", municipio="Getafe") == first
    assert state["promo_ids"] == {"https://example.org/a": first}


def test_collisions_get_a_numeric_suffix():
    state = empty_state()
    base = "emvs-madrid-madrid-vallecas-ensanche-34"
    # Fragments are part of the key: promotions sharing a page stay apart.
    assert get(state, "https://example.org/p#a") == base
    assert get(state, "https://example.org/p#b") == f"{base}-2"
    assert get(state, "https://example.org/p#c") == f"{base}-3"
    assert get(state, "https://example.org/p#b") == f"{base}-2"
    assert schema_errors(state, "state", SCHEMA_DIR) == []


@pytest.mark.parametrize("nombre", ["x" * 200, "y" * 99 + " " + "z" * 40])
def test_collision_on_long_names_stays_within_limit(nombre):
    state = empty_state()
    ids = [get(state, f"https://example.org/{n}", nombre=nombre) for n in range(12)]
    assert len(set(ids)) == 12
    assert all(len(i) <= 120 and SLUG.fullmatch(i) for i in ids)
    assert ids[1].endswith("-2")
    assert ids[11].endswith("-12")
    assert schema_errors(state, "state", SCHEMA_DIR) == []
