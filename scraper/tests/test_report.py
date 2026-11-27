"""Pending fields and the review report. Synthetic data only."""

import json
from datetime import date

import pytest
from conftest import SHA_A, SHA_B, build_promo

from vpo.core.merge import Aviso
from vpo.core.normalize import Municipios
from vpo.extraction import cache
from vpo.extraction.base import Descarte, ExtractionResult, FieldResult
from vpo.review.report import CAMPOS_CLAVE, campos_pendientes, construir_informe, escribir_informe, sin_resolver

TODAY = date(2026, 11, 27)
VERSION = "0.3.0"
MUNICIPIOS = Municipios([{"ine": "28079", "nombre": "Madrid", "nombre_ine": "Madrid"}])
INGRESOS = "/requisitos/ingresos_max_iprem"
EMPADRONAMIENTO = "/requisitos/empadronamiento"
REGISTRATION = {
    "ambito": "municipio",
    "municipio_ine": "28079",
    "anios_min": 3,
    "ininterrumpido": None,
    "alternativa_trabajo": None,
}


def candidate(campo, valor, confianza=0.9, pagina=2):
    return FieldResult(campo, valor, confianza, pagina, f"evidencia de {valor}", "REG-X-01", "pdf_texto")


def store(cache_dir, *candidatos, sha=SHA_A, necesita_ocr=False):
    entry = cache.CacheEntry(VERSION, "0" * 64, "28079", necesita_ocr, tuple(candidatos))
    cache.store(cache_dir, sha, entry)


def fake_resolver(*descartes):
    def resolver(candidatos, ctx, *, necesita_ocr=False, advertencias=()):
        assert ctx.municipio_ine == "28079" and ctx.fecha_ref == TODAY
        return ExtractionResult(descartes=tuple(descartes), necesita_ocr=necesita_ocr)

    return resolver


def report(promos, cache_dir, *, avisos=(), **kwargs):
    kwargs.setdefault("resolver", fake_resolver())
    return construir_informe(
        promos, avisos, cache_dir=cache_dir, municipios=MUNICIPIOS, today=TODAY, version=VERSION, **kwargs
    )


def with_requisitos(**changes):
    promo = build_promo()
    promo["requisitos"].update(changes)
    return promo


def test_key_fields_of_the_synthetic_promotion():
    assert campos_pendientes(build_promo()) == [EMPADRONAMIENTO, INGRESOS]
    assert set(campos_pendientes(build_promo())) <= set(CAMPOS_CLAVE)


def test_no_bases_means_nothing_to_review():
    promo = build_promo()
    promo["enlaces"]["bases"] = []
    assert campos_pendientes(promo, [Descarte("/requisitos/edad", "conflicto")]) == []


def test_unknown_state_municipality_and_rents():
    promo = build_promo(estado="desconocido")
    promo["ubicacion"]["municipio_ine"] = None
    promo["tipologias"][0]["renta_mensual_eur"] = None
    assert {"/estado", "/ubicacion/municipio_ine", "/tipologias"} <= set(campos_pendientes(promo))
    assert sin_resolver(build_promo(tipologias=[]), "/tipologias")
    assert not sin_resolver(build_promo(), "/tipologias")


def test_deadline_is_key_only_while_registration_is_open():
    promo = build_promo()
    promo["fechas"]["inscripcion_fin"] = None
    assert "/fechas/inscripcion_fin" in campos_pendientes(promo)
    promo["estado"] = "proxima"
    assert "/fechas/inscripcion_fin" not in campos_pendientes(promo)
    conflict = Descarte("/fechas/inscripcion_fin", "conflicto")
    assert "/fechas/inscripcion_fin" in campos_pendientes(promo, [conflict])


def test_requirements_resolved_by_table_or_by_not_being_demanded():
    table = [{"miembros_desde": 1, "miembros_hasta": None, "min_iprem": None, "max_iprem": 5.5}]
    assert INGRESOS not in campos_pendientes(with_requisitos(ingresos_por_miembros=table))
    promo = with_requisitos(no_exigidos=["empadronamiento", "ingresos_max_iprem"])
    assert campos_pendientes(promo) == []
    assert not sin_resolver(promo, EMPADRONAMIENTO)


def test_registration_without_years_stays_pending():
    assert sin_resolver(with_requisitos(empadronamiento={**REGISTRATION, "anios_min": None}), EMPADRONAMIENTO)
    assert not sin_resolver(with_requisitos(empadronamiento=REGISTRATION), EMPADRONAMIENTO)


@pytest.mark.parametrize("motivo", ["conflicto", "fuera_de_rango"])
def test_other_fields_are_pending_when_contradictory_or_implausible(motivo):
    descartes = [Descarte("/requisitos/edad", motivo), Descarte("/fechas/sorteo", motivo)]
    assert {"/requisitos/edad", "/fechas/sorteo"} <= set(campos_pendientes(build_promo(), descartes))


def test_other_fields_ignore_not_found_filled_values_and_pseudo_pointers():
    descartes = [
        Descarte("/requisitos/edad", "no_encontrado"),
        Descarte("/fechas/entrega_prevista", "conflicto"),  # already filled
        Descarte("/tipologias/*/garaje", "conflicto"),
    ]
    assert campos_pendientes(build_promo(), descartes) == [EMPADRONAMIENTO, INGRESOS]
    assert not sin_resolver(build_promo(), "/tipologias/*/garaje")
    assert sin_resolver(build_promo(), "/requisitos/edad")
    assert not sin_resolver(build_promo(), "/fechas/entrega_prevista")


def test_corrected_fields_are_not_pending():
    promo = build_promo()
    promo["meta"]["campos_override"] = [INGRESOS, EMPADRONAMIENTO]
    assert campos_pendientes(promo) == []


def test_report_gathers_reason_and_candidates(tmp_path):
    store(tmp_path, candidate(INGRESOS, 5.5), candidate(INGRESOS, 7.5, pagina=4))
    informe = report([build_promo()], tmp_path, resolver=fake_resolver(Descarte(INGRESOS, "conflicto")))
    [entry] = informe["revisiones"]
    assert entry["fuente_sha256"] == SHA_A and entry["detalle_completo"]
    fields = {item["campo"]: item for item in entry["campos"]}
    assert fields[INGRESOS]["motivo"] == "conflicto"
    assert [c["valor"] for c in fields[INGRESOS]["candidatos"]] == [5.5, 7.5]
    assert fields[INGRESOS]["candidatos"][1]["documento"] == "https://example.org/bases.pdf"
    assert fields[EMPADRONAMIENTO] == {"campo": EMPADRONAMIENTO, "motivo": "no_encontrado", "candidatos": []}
    assert informe["publicadas"] == ["demo-madrid-uno"]


def test_report_with_the_real_resolver_nulls_a_contradiction(tmp_path):
    store(tmp_path, candidate(INGRESOS, 5.5), candidate(INGRESOS, 7.5))
    informe = report([build_promo()], tmp_path, resolver=None)
    item = next(i for i in informe["revisiones"][0]["campos"] if i["campo"] == INGRESOS)
    assert item["motivo"] == "conflicto"
    assert sorted(c["valor"] for c in item["candidatos"]) == [5.5, 7.5]


def test_report_without_cache_or_with_a_scanned_document(tmp_path):
    [entry] = report([build_promo()], tmp_path)["revisiones"]
    assert not entry["detalle_completo"]
    assert {item["motivo"] for item in entry["campos"]} == {"no_disponible"}

    store(tmp_path, necesita_ocr=True)
    [entry] = report([build_promo()], tmp_path)["revisiones"]
    assert {item["motivo"] for item in entry["campos"]} == {"pdf_escaneado"}


def test_report_keeps_pending_fields_known_to_meta_without_cache(tmp_path):
    promo = build_promo()
    promo["meta"]["campos_pendientes"] = ["/requisitos/edad", "/fechas/entrega_prevista"]
    [entry] = report([promo], tmp_path)["revisiones"]
    pointers = [item["campo"] for item in entry["campos"]]
    assert "/requisitos/edad" in pointers and "/fechas/entrega_prevista" not in pointers


def test_complete_promotions_are_left_out(tmp_path):
    promo = with_requisitos(ingresos_max_iprem=5.5, empadronamiento=REGISTRATION)
    assert report([promo], tmp_path)["revisiones"] == []


def test_stale_corrections(tmp_path):
    promo = build_promo()
    avisos = [
        Aviso("override_desfasado", promo["id"], f"cambió la fuente de la corrección de: {INGRESOS}, /estado"),
        Aviso("override_huerfano", "no-existe", "no existe ninguna promoción con este id"),
    ]
    overrides = {"overrides": {promo["id"]: {"campos": {INGRESOS: {"fuente_sha256": SHA_B}}}}}
    informe = report([promo], tmp_path, avisos=avisos, overrides=overrides)
    [stale] = informe["overrides_desfasados"]
    assert stale["sha256_actual"] == SHA_A
    assert stale["campos"] == [
        {"campo": "/estado", "sha256_anterior": None},
        {"campo": INGRESOS, "sha256_anterior": SHA_B},
    ]
    assert [a["tipo"] for a in informe["avisos"]] == ["override_desfasado", "override_huerfano"]


def test_report_is_written_as_json(tmp_path):
    store(tmp_path, candidate(INGRESOS, 5.5))
    informe = report([build_promo()], tmp_path)
    path = tmp_path / "out" / "review-report.json"
    escribir_informe(path, informe)
    assert json.loads(path.read_text(encoding="utf-8")) == informe
