"""Orchestrator tests with fake adapters and a fake HTTP client: no network, no sleeping."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import pytest
from conftest import build_promo

import vpo.run as run_module
from vpo.__main__ import main
from vpo.core.jsonio import read_json, write_json
from vpo.run import UnknownSourceError, run
from vpo.sources.base import (
    DeadlineExceeded,
    Ficha,
    HttpStatusError,
    ListingError,
    Parsed,
    Response,
    SourceAdapter,
    procedencia_html,
)

TODAY = date(2026, 11, 27)
MANUAL_FILES = ("overrides.json", "iprem.json", "programas.json", "fuentes.json", "municipios.json")
SOURCES = ("fuente-a", "fuente-b")


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@dataclass
class Origin:
    """What one fake website currently publishes, and how it misbehaves."""

    id: str
    names: list[str]
    rents: dict[str, float] = field(default_factory=dict)
    broken: set[str] = field(default_factory=set)  # parsing raises
    changes: dict[str, dict] = field(default_factory=dict)  # name -> datos overrides
    down: Exception | None = None  # raised by listar
    footer: str = "visita 1"  # noise outside the hashed fragment
    parse_seconds: float = 0.0
    timeout_in: str | None = None  # name whose request hits the client deadline

    def listing_url(self) -> str:
        return f"https://{self.id}.example.org/listado"

    def url(self, name: str) -> str:
        return f"https://{self.id}.example.org/promo/{name}"


class FakeHttp:
    def __init__(self, origin: Origin, deadline: float, cache_dir) -> None:
        self.origin = origin
        self.deadline = deadline
        self.cache_dir = cache_dir
        self.log: list[Response] = []
        self.closed = False

    def get(self, url: str) -> Response:
        origin = self.origin
        if origin.timeout_in and url == origin.url(origin.timeout_in):
            raise DeadlineExceeded("sin tiempo")
        name = url.rsplit("/", 1)[-1]
        if url == origin.listing_url():
            body = f"<nav>{len(origin.names)} resultados</nav>"
        elif name in origin.names:
            body = f"<main><h1>{name}</h1><p>{origin.rents.get(name, 550.0)} euros</p></main>"
        else:
            raise HttpStatusError(url, 404)
        content = f"<html><body>{body}<footer>{origin.footer}</footer></body></html>".encode()
        response = Response(
            url=url,
            requested_url=url,
            status=200,
            content=content,
            encoding="utf-8",
            etag=None,
            last_modified=None,
        )
        self.log.append(response)
        return response

    def close(self) -> None:
        self.closed = True


class FakeAdapter(SourceAdapter):
    id = "fake"

    def __init__(self, config, municipios, origin: Origin, clock: FakeClock) -> None:
        super().__init__(config, municipios)
        self.origin = origin
        self.clock = clock

    def listar(self, http):
        if self.origin.down:
            raise self.origin.down
        http.get(self.origin.listing_url())
        return [Ficha(self.origin.url(name), name) for name in self.origin.names]

    def parsear_ficha(self, ficha, http):
        origin = self.origin
        self.clock.now += origin.parse_seconds
        http.get(ficha.url)
        if ficha.nombre in origin.broken:
            raise ValueError("el HTML ha cambiado")
        datos = build_promo(fuente_id=origin.id)
        del datos["id"], datos["meta"]
        datos["nombre"] = f"Promoción {ficha.nombre}"
        datos["tipologias"][0]["renta_mensual_eur"] = origin.rents.get(ficha.nombre, 550.0)
        datos["enlaces"] = {"oficial": ficha.url, "solicitud": None, "bases": []}
        datos |= origin.changes.get(ficha.nombre, {})
        return Parsed(datos, {"/nombre": procedencia_html(ficha.url, ficha.nombre)})

    def selector_hash(self):
        return "main"


class World:
    """A data folder plus the fake origins configured in it."""

    def __init__(self, data_dir) -> None:
        self.data_dir = data_dir
        self.clock = FakeClock()
        self.clients: list[FakeHttp] = []
        names = ["uno", "dos", "tres", "cuatro"]
        self.origins = {source_id: Origin(source_id, list(names)) for source_id in SOURCES}
        self.configure(*SOURCES)
        write_json(
            data_dir / "state.json",
            {"schema_version": 1, "ultima_ejecucion": None, "fuentes": {}, "documentos": {}, "promo_ids": {}},
        )

    def configure(self, *source_ids: str, inactive: tuple[str, ...] = ()) -> None:
        entries = [
            {
                "id": source_id,
                "nombre": source_id,
                "operador": {"id": source_id, "nombre": source_id, "tipo": "otro"},
                "url": f"https://{source_id}.example.org/",
                "url_verificada": False,
                "metodo": "httpx",
                "prioridad": 1,
                "activa": source_id not in inactive,
                "intervalo_s": 2,
                "timeout_s": 100,
                "notas": None,
            }
            for source_id in source_ids
        ]
        write_json(self.data_dir / "fuentes.json", {"schema_version": 1, "fuentes": entries})

    def run(self, today: date = TODAY, **kwargs):
        def adapter_factory(config, municipios):
            return FakeAdapter(config, municipios, self.origins[config["id"]], self.clock)

        def http_factory(config, deadline, cache_dir):
            client = FakeHttp(self.origins[config["id"]], deadline, cache_dir)
            self.clients.append(client)
            return client

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

    def source_path(self, source_id: str):
        return self.data_dir / "sources" / f"{source_id}.json"

    def source_bytes(self, source_id: str) -> bytes:
        return self.source_path(source_id).read_bytes()

    def promos(self, source_id: str) -> dict[str, dict]:
        """By the fake page name."""
        content = read_json(self.source_path(source_id))
        return {p["enlaces"]["oficial"].rsplit("/", 1)[-1]: p for p in content["promociones"]}

    def state(self) -> dict:
        return read_json(self.data_dir / "state.json")

    def health(self, source_id: str) -> dict:
        return self.state()["fuentes"][source_id]

    def owned_state(self, source_id: str) -> tuple[dict, dict]:
        """The promo_ids and documentos that belong to one source."""
        state = self.state()
        host = f"https://{source_id}.example.org/"
        ids = {url: i for url, i in state["promo_ids"].items() if url.startswith(host)}
        documents = {k: d for k, d in state["documentos"].items() if d["fuente_id"] == source_id}
        return ids, documents


@pytest.fixture
def world(data_dir) -> World:
    return World(data_dir)


def test_first_run_writes_sources_state_and_documents(world):
    reports = world.run()

    for source_id in SOURCES:
        report = reports[source_id]
        assert (report.estado, report.vistas, report.cambios, report.errores[1:]) == ("ok", 4, 4, [])
        content = read_json(world.source_path(source_id))
        ids = [p["id"] for p in content["promociones"]]
        assert content["fuente_id"] == source_id
        assert ids == sorted(ids) and len(set(ids)) == 4
        assert world.health(source_id)["promociones_vistas"] == 4
        assert world.health(source_id)["ultimo_error"] is None

    ids, documents = world.owned_state("fuente-a")
    origin = world.origins["fuente-a"]
    assert sorted(ids) == sorted(origin.url(name) for name in origin.names)
    by_url = {d["url"]: d for d in documents.values()}
    assert by_url[origin.url("uno")]["promo_ids"] == [ids[origin.url("uno")]]
    assert by_url[origin.url("uno")]["sha256_texto"] is not None
    # The listing has no <main>: recorded without a text hash, and reported.
    listing = by_url[origin.listing_url()]
    assert (listing["sha256_texto"], listing["promo_ids"]) == (None, [])
    assert origin.listing_url() in reports["fuente-a"].errores[0]


def test_http_clients_get_a_deadline_and_cache_dir_and_are_closed(world):
    world.origins["fuente-b"].down = ListingError("cambiado")
    world.run()
    assert [client.closed for client in world.clients] == [True, True]
    assert world.clients[0].deadline == 1100.0
    assert world.clients[0].cache_dir == world.data_dir.resolve().parent / ".cache" / "http"


def test_default_http_factory_uses_the_source_settings(world, monkeypatch):
    created = []

    def fake_client(**kwargs):
        created.append(kwargs)
        return FakeHttp(world.origins["fuente-a"], kwargs["deadline"], kwargs["cache_dir"])

    monkeypatch.setattr(run_module, "HttpClient", fake_client)
    report = run(
        world.data_dir,
        today=TODAY,
        now=datetime(2026, 11, 27, tzinfo=UTC),
        only={"fuente-a"},
        adapter_factory=lambda config, m: FakeAdapter(config, m, world.origins["fuente-a"], world.clock),
        clock=world.clock,
    )
    assert report.fuentes[0].estado == "ok"
    assert (created[0]["min_interval_s"], created[0]["deadline"]) == (2, 1100.0)
    assert created[0]["cache_dir"].name == "http"


@pytest.mark.parametrize("failure", ["exception", "empty", "duplicate"])
def test_one_source_down_leaves_the_other_unaffected(world, failure):
    world.run()
    a, b = world.origins["fuente-a"], world.origins["fuente-b"]
    good = world.source_bytes("fuente-a")
    ids, documents = world.owned_state("fuente-a")

    if failure == "exception":
        a.down = HttpStatusError(a.listing_url(), 503)
    elif failure == "empty":
        a.names = []
    else:
        a.names = ["uno", "uno"]
    b.rents["uno"] = 600.0
    reports = world.run(today=TODAY + timedelta(days=1))

    assert reports["fuente-a"].estado == "error"
    assert reports["fuente-a"].cambios == 0 and reports["fuente-a"].errores
    assert world.source_bytes("fuente-a") == good
    assert world.owned_state("fuente-a") == (ids, documents)
    health = world.health("fuente-a")
    assert (health["estado"], health["fallos_consecutivos"]) == ("error", 1)
    assert health["ultimo_exito"].startswith("2026-11-27")
    assert health["ultimo_error"]

    assert (reports["fuente-b"].estado, reports["fuente-b"].cambios) == ("ok", 1)
    assert world.promos("fuente-b")["uno"]["tipologias"][0]["renta_mensual_eur"] == 600.0
    assert world.health("fuente-b")["ultimo_exito"].startswith("2026-11-28")


def test_a_source_without_adapter_fails_alone(world):
    world.configure("fuente-a", "sin-adaptador")

    def adapter_factory(config, municipios):
        if config["id"] == "sin-adaptador":
            raise LookupError("no hay adaptador")
        return FakeAdapter(config, municipios, world.origins[config["id"]], world.clock)

    report = run(
        world.data_dir,
        today=TODAY,
        now=datetime(2026, 11, 27, tzinfo=UTC),
        adapter_factory=adapter_factory,
        http_factory=lambda config, d, c: FakeHttp(world.origins[config["id"]], d, c),
    )
    assert [r.estado for r in report.fuentes] == ["ok", "error"]
    assert not world.source_path("sin-adaptador").exists()


INVALID = {
    "schema": {"viviendas_total": "muchas"},
    "fuente_id": {"fuente_id": "otra"},
    "municipio": {
        "ubicacion": {
            "municipio_ine": "28999",
            "municipio": "Inventado",
            "distrito": None,
            "direccion": None,
            "lat": None,
            "lon": None,
        }
    },
}


@pytest.mark.parametrize("failure", ["exception", *INVALID])
def test_a_failed_ficha_keeps_its_previous_version(world, failure):
    world.run()
    origin = world.origins["fuente-a"]
    before = world.promos("fuente-a")

    if failure == "exception":
        origin.broken = {"uno", "nueva"}
    else:
        origin.changes = {"uno": INVALID[failure], "nueva": INVALID[failure]}
    origin.names = [*origin.names, "nueva"]
    origin.rents["dos"] = 700.0
    report = world.run(today=TODAY + timedelta(days=1))["fuente-a"]

    after = world.promos("fuente-a")
    assert (report.estado, report.vistas, report.cambios) == ("ok", 5, 1)
    assert after["uno"] == before["uno"]  # untouched, and not treated as disappeared
    assert after["dos"]["tipologias"][0]["renta_mensual_eur"] == 700.0
    assert "nueva" not in after
    assert origin.url("nueva") not in world.state()["promo_ids"]
    assert sum(origin.url(n) in error for n in ("uno", "nueva") for error in report.errores) == 2
    assert world.health("fuente-a")["fallos_consecutivos"] == 0
    _, documents = world.owned_state("fuente-a")
    by_url = {d["url"]: d for d in documents.values()}
    assert by_url[origin.url("uno")]["promo_ids"] == [before["uno"]["id"]]
    assert by_url[origin.url("nueva")]["promo_ids"] == []


def test_exactly_half_failing_is_still_ok(world):
    world.origins["fuente-a"].broken = {"uno", "dos"}
    assert world.run()["fuente-a"].estado == "ok"


def test_more_than_half_failing_is_degraded_and_still_writes(world):
    world.run()
    origin = world.origins["fuente-a"]
    before = world.promos("fuente-a")

    origin.broken = {"uno", "dos", "tres"}
    origin.rents["cuatro"] = 800.0
    report = world.run(today=TODAY + timedelta(days=1))["fuente-a"]

    assert report.estado == "degradado"
    after = world.promos("fuente-a")
    assert after["cuatro"]["tipologias"][0]["renta_mensual_eur"] == 800.0
    assert [after[n] for n in ("uno", "dos", "tres")] == [before[n] for n in ("uno", "dos", "tres")]
    health = world.health("fuente-a")
    assert (health["estado"], health["fallos_consecutivos"]) == ("degradado", 0)
    assert health["ultimo_exito"].startswith("2026-11-27")


def test_every_ficha_failing_is_an_error_and_touches_nothing(world):
    world.run()
    origin = world.origins["fuente-a"]
    good = world.source_bytes("fuente-a")
    owned = world.owned_state("fuente-a")

    origin.broken = {*origin.names, "nueva"}
    origin.names = [*origin.names, "nueva"]
    report = world.run(today=TODAY + timedelta(days=1))["fuente-a"]

    assert (report.estado, report.vistas, report.cambios) == ("error", 5, 0)
    assert world.source_bytes("fuente-a") == good
    assert world.owned_state("fuente-a") == owned
    assert world.health("fuente-a")["fallos_consecutivos"] == 1


def test_a_first_run_that_fails_creates_no_file_and_freezes_no_id(world):
    world.origins["fuente-a"].broken = set(world.origins["fuente-a"].names)
    assert world.run()["fuente-a"].estado == "error"
    assert not world.source_path("fuente-a").exists()
    assert world.owned_state("fuente-a") == ({}, {})


def without_run_noise(state: dict) -> dict:
    del state["ultima_ejecucion"]
    for health in state["fuentes"].values():
        del health["ultima_ejecucion"], health["ultimo_exito"], health["duracion_s"]
    for document in state["documentos"].values():
        del document["ultima_comprobacion"]
    return state


def test_second_run_with_unchanged_origin_produces_no_diff(world):
    world.run()
    files = {source_id: world.source_bytes(source_id) for source_id in SOURCES}
    state = without_run_noise(world.state())

    for origin in world.origins.values():
        origin.footer = "visita 2"  # bytes change, the relevant fragment does not
        origin.parse_seconds = 1.5
    reports = world.run(today=TODAY + timedelta(days=3))

    assert [r.cambios for r in reports.values()] == [0, 0]
    assert {source_id: world.source_bytes(source_id) for source_id in SOURCES} == files
    assert without_run_noise(world.state()) == state


def test_a_renamed_promotion_keeps_its_id(world):
    world.run()
    first = world.promos("fuente-a")["uno"]["id"]
    world.origins["fuente-a"].changes = {"uno": {"nombre": "Otro nombre comercial"}}
    world.run(today=TODAY + timedelta(days=1))
    promo = world.promos("fuente-a")["uno"]
    assert (promo["id"], promo["nombre"]) == (first, "Otro nombre comercial")


def test_a_disappeared_promotion_is_kept_and_finished_after_30_days(world):
    world.run()
    origin = world.origins["fuente-a"]
    gone_id = world.promos("fuente-a")["uno"]["id"]
    origin.names = ["dos", "tres", "cuatro"]

    report = world.run(today=TODAY + timedelta(days=1))["fuente-a"]
    gone = world.promos("fuente-a")["uno"]
    assert (report.estado, report.vistas, report.cambios) == ("ok", 3, 1)
    assert gone["id"] == gone_id
    assert gone["meta"]["activa_en_fuente"] is False
    assert gone["estado"] == "inscripcion_abierta"

    world.run(today=TODAY + timedelta(days=15))
    assert world.promos("fuente-a")["uno"]["estado"] == "inscripcion_abierta"

    world.run(today=TODAY + timedelta(days=31))
    finished = world.promos("fuente-a")["uno"]
    assert finished["estado"] == "finalizada"
    assert finished["meta"]["activa_en_fuente"] is False

    after = world.source_bytes("fuente-a")
    assert world.run(today=TODAY + timedelta(days=40))["fuente-a"].cambios == 0
    assert world.source_bytes("fuente-a") == after


@pytest.mark.parametrize("how", ["between_fichas", "inside_a_request"])
def test_deadline_exceeded_aborts_only_that_source(world, how):
    world.run()
    origin = world.origins["fuente-a"]
    good = world.source_bytes("fuente-a")
    owned = world.owned_state("fuente-a")
    origin.rents["uno"] = 900.0
    if how == "between_fichas":
        origin.parse_seconds = 60.0  # the third ficha starts past the 100 s limit
    else:
        origin.timeout_in = "tres"

    reports = world.run(today=TODAY + timedelta(days=1))

    assert reports["fuente-a"].estado == "error"
    assert "DeadlineExceeded" in reports["fuente-a"].errores[0]
    assert world.source_bytes("fuente-a") == good
    assert world.owned_state("fuente-a") == owned
    assert reports["fuente-b"].estado == "ok"
    if how == "between_fichas":
        assert reports["fuente-a"].duracion_s == 120.0
        assert len(world.clients[2].log) == 3  # listing and two fichas


def test_consecutive_failures_are_counted_and_reset(world):
    origin = world.origins["fuente-a"]
    origin.down = ListingError("cambiado")
    for expected in (1, 2, 3):
        world.run(today=TODAY + timedelta(days=expected))
        assert world.health("fuente-a")["fallos_consecutivos"] == expected
    assert world.health("fuente-a")["ultimo_exito"] is None

    origin.down = None
    world.run(today=TODAY + timedelta(days=4))
    health = world.health("fuente-a")
    assert (health["estado"], health["fallos_consecutivos"], health["ultimo_error"]) == ("ok", 0, None)


def test_manual_files_are_untouched_and_the_result_merges_and_validates(world):
    before = {name: (world.data_dir / name).read_bytes() for name in MANUAL_FILES}
    world.run()
    world.origins["fuente-a"].down = ListingError("cambiado")
    world.origins["fuente-b"].names = ["uno", "dos"]
    world.origins["fuente-b"].broken = {"dos"}
    world.run(today=TODAY + timedelta(days=1))

    assert {name: (world.data_dir / name).read_bytes() for name in MANUAL_FILES} == before
    arguments = ["--data-dir", str(world.data_dir), "--hoy", "2026-11-28"]
    assert main(["merge", *arguments]) == 0
    assert main(["validate", *arguments]) == 0
    assert len(read_json(world.data_dir / "promociones.json")["promociones"]) == 9  # 4 + 4 + demo


def test_only_runs_the_requested_sources(world):
    assert list(world.run(only={"fuente-b"})) == ["fuente-b"]
    assert not world.source_path("fuente-a").exists()


@pytest.mark.parametrize("requested", ["no-existe", "fuente-a"])
def test_only_rejects_unknown_and_inactive_sources(world, requested):
    world.configure(*SOURCES, inactive=("fuente-a",))
    state = (world.data_dir / "state.json").read_bytes()
    with pytest.raises(UnknownSourceError, match=requested):
        world.run(only={requested, "fuente-b"})
    assert (world.data_dir / "state.json").read_bytes() == state
    assert not world.clients


def test_inactive_sources_are_skipped(world):
    world.configure(*SOURCES, inactive=("fuente-a",))
    assert list(world.run()) == ["fuente-b"]


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("state.json", "{ roto"),
        ("sources/fuente-b.json", "{ roto"),
        ("sources/fuente-b.json", '{"schema_version": 1}'),
        ("schema/promocion.schema.json", "{ roto"),
    ],
)
def test_global_problems_propagate_before_any_source_runs(world, name, content):
    (world.data_dir / name).write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        world.run()
    assert not world.clients
    assert not world.source_path("fuente-a").exists()
