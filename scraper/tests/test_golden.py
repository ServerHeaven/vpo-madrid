"""Golden tests on real PDFs (ARCHITECTURE.md §5.4).

Every tests/fixtures/pdf/<name>.pdf has tests/golden/pdf/<name>.json, written by hand from the
document itself:

{
  "fixture": "<name>.pdf",
  "fuente_id": "emvs-madrid",
  "municipio_ine": "28079",            // or null when the document covers several municipalities
  "fecha_ref": "2026-11-27",
  "necesita_ocr": false,
  "esperado": [                          // EVERY value the document states for a supported field
    {"campo": "/requisitos/ingresos_max_iprem", "valor": 5.5, "pagina": 3, "cita": "…literal…"}
  ],                                     // optional "regla": "REG-IPREM-01"
  "conflictos": ["/requisitos/edad"],  // fields the document states with contradicting values
  "notas": "free text"
}

A value extracted for a field that is not listed counts as a false positive. Free-text notes
(/requisitos/otros) are not measured.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from functools import cache
from pathlib import Path

import pytest
from conftest import DATA_DIR

from vpo.core.jsonio import read_json
from vpo.core.normalize import Municipios
from vpo.extraction.base import ExtractionContext, ExtractionResult
from vpo.extraction.documents.pdf import leer_pdf
from vpo.extraction.pipeline import extraer

PDF_DIR = Path(__file__).parent / "fixtures" / "pdf"
GOLDEN_DIR = Path(__file__).parent / "golden" / "pdf"
NAMES = sorted(path.stem for path in GOLDEN_DIR.glob("*.json"))
NOT_MEASURED = {"/requisitos/otros"}
ROW_KEYS = ("dormitorios", "superficie_util_m2", "renta_mensual_eur", "renta_mensual_max_eur", "num_viviendas")
MIN_PRECISION = 0.98


def golden(name: str) -> dict:
    return read_json(GOLDEN_DIR / f"{name}.json")


@cache
def result_of(name: str) -> ExtractionResult:
    expected = golden(name)
    document = leer_pdf((PDF_DIR / expected["fixture"]).read_bytes(), url=f"https://example.org/{name}.pdf")
    context = ExtractionContext(
        fuente_id=expected["fuente_id"],
        fecha_ref=date.fromisoformat(expected["fecha_ref"]),
        municipios=Municipios.load(DATA_DIR),
        municipio_ine=expected["municipio_ine"],
    )
    return extraer(document, context)


def _number(value):
    return float(value) if isinstance(value, int) and not isinstance(value, bool) else value


def comparable(campo: str, valor):
    """Order-insensitive form of a value; tipologias are compared on the measured keys only."""
    if campo == "/tipologias":
        # 783 and 783.0 are the same rent: unify before sorting by text.
        return sorted((tuple(_number(row.get(key)) for key in ROW_KEYS) for row in valor), key=repr)
    return valor


def pairs(items) -> list[tuple[str, str]]:
    """(campo, canonical value). /requisitos/no_exigidos yields one pair per value."""
    return [
        (campo, repr(_sorted_dicts(comparable(campo, valor))))
        for campo, valor in items
        if campo not in NOT_MEASURED
    ]


def _sorted_dicts(value):
    if isinstance(value, dict):
        return {key: _sorted_dicts(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_sorted_dicts(item) for item in value]
    if isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return value


def counts(name: str) -> tuple[Counter, Counter]:
    expected = pairs((item["campo"], item["valor"]) for item in golden(name)["esperado"])
    found = pairs((r.campo, r.valor) for r in result_of(name).campos)
    return Counter(expected), Counter(found)


def test_there_are_enough_real_documents():
    assert len(NAMES) >= 10
    assert sorted(path.stem for path in PDF_DIR.glob("*.pdf")) == NAMES


@pytest.mark.parametrize("name", NAMES)
def test_nothing_wrong_is_extracted(name):
    expected, found = counts(name)
    assert not (found - expected), f"valores que el golden no recoge: {sorted((found - expected).elements())}"


@pytest.mark.parametrize("name", NAMES)
def test_scanned_and_conflicts(name):
    expected, result = golden(name), result_of(name)
    assert result.necesita_ocr is expected["necesita_ocr"]
    accepted = {r.campo for r in result.campos}
    conflicting = {d.campo for d in result.descartes if d.motivo == "conflicto"}
    for campo in expected["conflictos"]:
        assert campo not in accepted
        assert campo in conflicting


@pytest.mark.parametrize("name", NAMES)
def test_expected_rules_still_fire(name):
    rules = {(r.campo, r.regla) for r in result_of(name).campos}
    found = {r.campo for r in result_of(name).campos}
    for item in golden(name)["esperado"]:
        if item.get("regla") and item["campo"] in found:
            assert (item["campo"], item["regla"]) in rules


def metrics() -> dict[str, tuple[int, int, int]]:
    """campo -> (correct, extracted, expected), plus the total under "TOTAL"."""
    totals: dict[str, list[int]] = {}
    for name in NAMES:
        expected, found = counts(name)
        for index, counter in enumerate((expected & found, found, expected)):
            for (campo, _), number in counter.items():
                for key in (campo, "TOTAL"):
                    totals.setdefault(key, [0, 0, 0])[index] += number
    return {key: tuple(value) for key, value in totals.items()}


def metrics_table() -> str:
    lines = [f"{'campo':<38} {'aciertos':>8} {'extraídos':>9} {'esperados':>9} {'precisión':>9} {'cobertura':>9}"]
    table = metrics()
    for campo in sorted(table, key=lambda c: (c == "TOTAL", c)):
        correct, extracted, expected = table[campo]
        precision = f"{correct / extracted:.2f}" if extracted else "-"
        coverage = f"{correct / expected:.2f}" if expected else "-"
        lines.append(f"{campo:<38} {correct:>8} {extracted:>9} {expected:>9} {precision:>9} {coverage:>9}")
    return "\n".join(lines)


def test_precision_report():
    """Precision is blocking; coverage (target 0.7) is only reported."""
    print("\n" + metrics_table())
    correct, extracted, _ = metrics()["TOTAL"]
    assert extracted > 0
    assert correct / extracted >= MIN_PRECISION, metrics_table()
