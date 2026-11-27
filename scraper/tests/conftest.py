"""Synthetic fixtures. None of these promotions exist."""

import copy
import shutil
from pathlib import Path

import pytest

from vpo.core.jsonio import write_json
from vpo.core.validate import schema_errors

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SCHEMA_DIR = DATA_DIR / "schema"
SHA_A = "a" * 64
SHA_B = "b" * 64


def build_promo(promo_id: str = "demo-madrid-uno", *, fuente_id: str = "demo", **changes) -> dict:
    promo = {
        "id": promo_id,
        "nombre": "Promoción sintética",
        "operador": {"id": "demo", "nombre": "Operador ficticio", "tipo": "otro"},
        "fuente_id": fuente_id,
        "regimen": "VPPB",
        "programa": None,
        "modalidad": "alquiler",
        "estado": "inscripcion_abierta",
        "ubicacion": {
            "municipio_ine": "28079",
            "municipio": "Madrid",
            "distrito": None,
            "direccion": None,
            "lat": None,
            "lon": None,
        },
        "viviendas_total": 10,
        "tipologias": [
            {
                "dormitorios": 2,
                "superficie_util_m2": 60.5,
                "renta_mensual_eur": 550.0,
                "renta_mensual_max_eur": None,
                "num_viviendas": 10,
                "garaje": {"disponibilidad": "incluido", "precio_mensual_eur": None},
                "trastero": {"disponibilidad": "desconocido", "precio_mensual_eur": None},
                "adaptada_pmr": None,
            }
        ],
        "requisitos": {
            "ingresos_min_iprem": None,
            "ingresos_max_iprem": None,
            "ingresos_por_miembros": None,
            "iprem_pagas": None,
            "iprem_ejercicio": None,
            "tasa_esfuerzo_max": None,
            "empadronamiento": None,
            "edad": None,
            "no_titular_vivienda": None,
            "no_exigidos": [],
            "otros": [],
        },
        "fechas": {
            "inscripcion_inicio": "2026-11-01",
            "inscripcion_fin": "2026-12-15",
            "sorteo": None,
            "entrega_prevista": "2027-T2",
        },
        "enlaces": {
            "oficial": "https://example.org/promo",
            "solicitud": None,
            "bases": [
                {
                    "url": "https://example.org/bases.pdf",
                    "titulo": "Bases",
                    "sha256": SHA_A,
                    "detectado_en": "2026-11-01",
                    "es_principal": True,
                }
            ],
        },
        "meta": {
            "primera_deteccion": "2026-11-01",
            "ultima_modificacion": "2026-11-01",
            "activa_en_fuente": True,
            "campos_pendientes": ["/requisitos/ingresos_max_iprem"],
            "campos_override": [],
            "procedencia": {},
            "extractor_version": "0.1.0",
        },
    }
    promo.update(copy.deepcopy(changes))
    return promo


def build_field(valor, *, sha: str | None = SHA_A, fecha: str = "2026-11-20") -> dict:
    return {"valor": valor, "motivo": "Revisado en las bases", "autor": "test", "fecha": fecha, "fuente_sha256": sha}


def build_overrides(entries: dict | None = None, manual: list | None = None) -> dict:
    return {"schema_version": 1, "overrides": entries or {}, "promociones_manuales": manual or []}


def build_entry(campos: dict | None = None, *, ocultar: bool = False) -> dict:
    return {"campos": campos or {}, "ocultar": ocultar, "nota_publica": None}


def validate_promo(promo: dict) -> list[str]:
    return schema_errors(promo, "promocion", SCHEMA_DIR)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A writable copy of the real data/ folder with one synthetic source."""
    target = tmp_path / "data"
    shutil.copytree(DATA_DIR, target)
    for path in (target / "sources").glob("*.json"):
        path.unlink()
    write_json(
        target / "overrides.json",
        build_overrides({"demo-madrid-uno": build_entry({"/requisitos/ingresos_max_iprem": build_field(5.5)})}),
    )
    write_json(
        target / "promociones.json",
        {"schema_version": 1, "generado_en": "2026-01-01T00:00:00Z", "promociones": []},
    )
    write_json(
        target / "sources" / "demo.json",
        {"schema_version": 1, "fuente_id": "demo", "promociones": [build_promo()]},
    )
    return target
