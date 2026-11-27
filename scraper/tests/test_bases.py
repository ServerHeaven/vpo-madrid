"""End to end with bases PDFs: orchestrator, extraction, merge and review. Synthetic documents."""

from __future__ import annotations

from datetime import date

import pymupdf
import pytest
from conftest import build_entry, build_field, build_overrides
from test_run import TODAY, FakeAdapter, FakeHttp, World

import vpo.documentos as documentos_module
from vpo.__main__ import build_report, main
from vpo.core.jsonio import read_json, write_json
from vpo.extraction import pipeline
from vpo.run import run
from vpo.sources.base import DocumentoRef, HttpStatusError, Response, requisitos_desconocidos

FILLER = "Este documento describe las condiciones de la convocatoria de viviendas en alquiler."
CLEAR = [
    "REQUISITOS DE LOS SOLICITANTES",
    "Los ingresos de la unidad de convivencia no podrán superar 5,5 veces el IPREM.",
    FILLER,
]
CONTRADICTORY = [
    "REQUISITOS DE LOS SOLICITANTES",
    "Los ingresos de la unidad de convivencia no podrán superar 5,5 veces el IPREM.",
    FILLER,
    "Los ingresos de la unidad de convivencia no podrán superar 7,5 veces el IPREM.",
]
MAX = "/requisitos/ingresos_max_iprem"


def make_pdf(lines: list[str]) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    for number, line in enumerate(lines):
        page.insert_text((50, 80 + 40 * number), line, fontsize=10)
    return document.tobytes()


class PdfWorld(World):
    """One source whose promotion "uno" links a bases PDF."""

    def __init__(self, data_dir) -> None:
        super().__init__(data_dir)
        self.configure("fuente-a")
        write_json(data_dir / "overrides.json", build_overrides())
        origin = self.origins["fuente-a"]
        origin.names = ["uno"]
        requisitos = requisitos_desconocidos()
        origin.changes["uno"] = {"requisitos": requisitos}
        self.pdf: bytes | None = make_pdf(CLEAR)
        self.pdf_url = "https://fuente-a.example.org/docs/bases.pdf"

    def run(self, today: date = TODAY, **kwargs):
        world = self

        class Http(FakeHttp):
            def get(self, url: str) -> Response:
                if url != world.pdf_url:
                    return super().get(url)
                if world.pdf is None:
                    raise HttpStatusError(url, 503)
                response = Response(url, url, 200, world.pdf, None, None, None)
                self.log.append(response)
                return response

        class Adapter(FakeAdapter):
            def documentos(self, ficha, http):
                return [DocumentoRef(world.pdf_url, "Bases", True)]

        def adapter_factory(config, municipios):
            return Adapter(config, municipios, world.origins[config["id"]], world.clock)

        def http_factory(config, deadline, cache_dir):
            return Http(world.origins[config["id"]], deadline, cache_dir)

        from datetime import UTC, datetime

        report = run(
            self.data_dir,
            today=today,
            now=datetime(today.year, today.month, today.day, 5, 0, tzinfo=UTC),
            adapter_factory=adapter_factory,
            http_factory=http_factory,
            clock=self.clock,
            **kwargs,
        )
        return {source.fuente_id: source for source in report.fuentes}

    def promo(self) -> dict:
        return read_json(self.source_path("fuente-a"))["promociones"][0]

    def pdf_record(self) -> dict:
        return next(d for d in self.state()["documentos"].values() if d["tipo"] == "pdf")


@pytest.fixture
def bases(data_dir) -> PdfWorld:
    for path in (data_dir / "sources").glob("*.json"):
        path.unlink()
    return PdfWorld(data_dir)


def test_a_value_from_the_pdf_reaches_the_promotion_with_its_provenance(bases):
    report = bases.run()["fuente-a"]
    assert report.estado == "ok"
    promo = bases.promo()
    assert promo["requisitos"]["ingresos_max_iprem"] == 5.5
    assert promo["meta"]["procedencia"][MAX]["metodo"] == "pdf_texto"
    assert promo["meta"]["procedencia"][MAX]["pagina"] == 1
    [doc] = promo["enlaces"]["bases"]
    assert (doc["url"], doc["es_principal"], doc["detectado_en"]) == (bases.pdf_url, True, "2026-11-27")
    record = bases.pdf_record()
    assert record["sha256_bytes"] == doc["sha256"]
    assert record["promo_ids"] == [promo["id"]]
    assert record["extractor_version"] == promo["meta"]["extractor_version"]
    assert MAX not in promo["meta"]["campos_pendientes"]
    # The PDF is not recorded as an HTML page too.
    assert [d["tipo"] for d in bases.state()["documentos"].values() if d["url"] == bases.pdf_url] == ["pdf"]


def test_an_unchanged_pdf_is_not_extracted_again_and_produces_no_diff(bases, monkeypatch):
    bases.run()
    source = bases.source_bytes("fuente-a")
    record = bases.pdf_record()

    def forbidden(*args, **kwargs):
        raise AssertionError("no debía reextraer")

    monkeypatch.setattr(pipeline, "extraer_candidatos", forbidden)
    assert bases.run(today=date(2026, 11, 28))["fuente-a"].errores[1:] == []
    assert bases.source_bytes("fuente-a") == source
    assert bases.pdf_record() == record | {"ultima_comprobacion": "2026-11-28"}


def test_forced_reparse_extracts_again(bases, monkeypatch):
    bases.run()
    calls = []
    real = pipeline.extraer_candidatos
    monkeypatch.setattr(pipeline, "extraer_candidatos", lambda *a, **k: calls.append(1) or real(*a, **k))
    bases.run(force_reparse=True)
    assert calls == [1]


def test_a_new_minor_version_extracts_again(bases, monkeypatch):
    bases.run()
    calls = []
    real = pipeline.extraer_candidatos
    monkeypatch.setattr(pipeline, "extraer_candidatos", lambda *a, **k: calls.append(1) or real(*a, **k))
    monkeypatch.setattr(documentos_module, "__version__", "0.4.0")
    bases.run()
    assert calls == [1]
    assert bases.pdf_record()["extractor_version"] == "0.4.0"


def test_contradicting_values_give_null_and_both_candidates_in_the_report(bases):
    bases.pdf = make_pdf(CONTRADICTORY)
    bases.run()
    promo = bases.promo()
    assert promo["requisitos"]["ingresos_max_iprem"] is None
    assert MAX in promo["meta"]["campos_pendientes"]

    assert main(["merge", "--data-dir", str(bases.data_dir), "--hoy", "2026-11-27"]) == 0
    report = build_report(bases.data_dir, TODAY)
    text = repr(report)
    assert "conflicto" in text and "5,5 veces" in text and "7,5 veces" in text
    assert (bases.data_dir / "review-report.json").is_file()


def test_a_correction_removes_the_pending_field(bases):
    bases.pdf = make_pdf(CONTRADICTORY)
    bases.run()
    promo = bases.promo()
    entry = build_entry({MAX: build_field(5.5, sha=promo["enlaces"]["bases"][0]["sha256"])})
    write_json(bases.data_dir / "overrides.json", build_overrides({promo["id"]: entry}))
    assert main(["merge", "--data-dir", str(bases.data_dir), "--hoy", "2026-11-27"]) == 0
    [merged] = [p for p in read_json(bases.data_dir / "promociones.json")["promociones"] if p["id"] == promo["id"]]
    assert merged["requisitos"]["ingresos_max_iprem"] == 5.5
    assert MAX not in merged["meta"]["campos_pendientes"]


def test_declaring_a_requirement_as_not_demanded_removes_it_from_pending(bases):
    bases.run()
    promo = bases.promo()
    assert "/requisitos/empadronamiento" in promo["meta"]["campos_pendientes"]
    entry = build_entry({"/requisitos/no_exigidos": build_field(["empadronamiento"], sha=None)})
    write_json(bases.data_dir / "overrides.json", build_overrides({promo["id"]: entry}))
    assert main(["merge", "--data-dir", str(bases.data_dir), "--hoy", "2026-11-27"]) == 0
    [merged] = read_json(bases.data_dir / "promociones.json")["promociones"]
    assert "/requisitos/empadronamiento" not in merged["meta"]["campos_pendientes"]
    assert main(["validate", "--data-dir", str(bases.data_dir), "--hoy", "2026-11-27"]) == 0


def test_declaring_as_not_demanded_a_field_with_value_fails_validation(bases):
    bases.run()
    promo = bases.promo()
    entry = build_entry({"/requisitos/no_exigidos": build_field(["ingresos_max_iprem"], sha=None)})
    write_json(bases.data_dir / "overrides.json", build_overrides({promo["id"]: entry}))
    assert main(["validate", "--data-dir", str(bases.data_dir), "--hoy", "2026-11-27"]) == 1


def test_a_pdf_that_stops_downloading_keeps_the_previous_data(bases):
    bases.run()
    source = bases.source_bytes("fuente-a")
    bases.pdf = None
    report = bases.run()["fuente-a"]
    # Its only ficha failed, so the source is an error and its file is not touched.
    assert report.estado == "error"
    assert bases.source_bytes("fuente-a") == source


def test_a_new_pdf_that_cannot_be_read_is_only_a_warning(bases):
    bases.pdf = b"<html>no es un PDF</html>"
    report = bases.run()["fuente-a"]
    assert report.estado == "ok"
    assert any(bases.pdf_url in text for text in report.errores)
    assert bases.promo()["enlaces"]["bases"] == []
    assert bases.promo()["meta"]["campos_pendientes"] == []


def test_manual_files_are_never_written(bases):
    names = ("overrides.json", "iprem.json", "programas.json", "fuentes.json", "municipios.json")
    before = {name: (bases.data_dir / name).read_bytes() for name in names}
    bases.run()
    assert {name: (bases.data_dir / name).read_bytes() for name in names} == before
