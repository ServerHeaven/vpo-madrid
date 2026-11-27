"""GitHub Issues synchronisation with ``gh`` replaced by an in-memory GitHub."""

import json
import re
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from conftest import (
    SCHEMA_DIR,
    SHA_A,
    SHA_B,
    build_entry,
    build_field,
    build_overrides,
    build_promo,
    validate_promo,
)

from vpo.core.merge import Aviso, merge
from vpo.core.normalize import Municipios
from vpo.core.validate import schema_errors
from vpo.extraction import cache
from vpo.extraction.base import FieldResult
from vpo.review.issues import ETIQUETAS, MAX_CUERPO, GhClient, cuerpo_revision, sync_health, sync_issues
from vpo.review.report import construir_informe

ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 11, 27)
VERSION = "0.3.0"
REPO = "ServerHeaven/vpo-madrid"
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


class FakeGitHub:
    """Runner that understands the few ``gh`` commands the module uses."""

    def __init__(self):
        self.issues: dict[int, dict] = {}
        self.labels: set[str] = set()
        self.calls: list[list[str]] = []
        self.fails = lambda command, body: False

    def __call__(self, command, **kwargs):
        assert isinstance(command, list) and command[0] == "gh" and not kwargs.get("shell")
        assert command[-2:] == ["--repo", REPO]
        self.calls.append(command)
        body = kwargs.get("input")
        if self.fails(command, body):
            return subprocess.CompletedProcess(command, 1, "", "HTTP 502")
        group, action, *args = command[1:-2]
        options = dict(zip(args, args[1:], strict=False))
        title = next((a.removeprefix("--title=") for a in args if a.startswith("--title=")), None)
        out = ""
        if group == "label":
            self.labels.add(args[0])
        elif action == "list":
            out = json.dumps(
                [
                    {"number": n, "title": i["title"], "body": i["body"].replace("\n", "\r\n")}
                    for n, i in self.issues.items()
                    if i["open"] and options["--label"] in i["labels"]
                ]
            )
        elif action == "create":
            assert options["--body-file"] == "-" and options["--label"] in self.labels
            number = len(self.issues) + 1
            self.issues[number] = {
                "title": title,
                "body": body,
                "labels": [options["--label"]],
                "open": True,
                "comments": [],
            }
            out = f"https://github.com/{REPO}/issues/{number}\n"
        else:
            issue = self.issues[int(args[0])]
            if action == "edit":
                issue["title"], issue["body"] = title, body
            elif action == "comment":
                issue["comments"].append(body)
            elif action == "close":
                issue["open"] = False
        return subprocess.CompletedProcess(command, 0, out, "")

    def open(self, label="needs-review"):
        return [i for i in self.issues.values() if i["open"] and label in i["labels"]]

    def writes(self):
        return [c for c in self.calls if c[1] == "issue" and c[2] != "list"]


@pytest.fixture
def github():
    return FakeGitHub()


@pytest.fixture
def client(github):
    return GhClient(REPO, runner=github)


def candidate(campo, valor, pagina=2, evidencia=None):
    evidencia = evidencia or f"no superen {valor} veces el IPREM"
    return FieldResult(campo, valor, 0.9, pagina, evidencia, "REG-IPREM-01", "pdf_texto")


def store(cache_dir, *candidatos):
    cache.store(cache_dir, SHA_A, cache.CacheEntry(VERSION, "0" * 64, "28079", False, tuple(candidatos)))


def pipeline_run(tmp_path, promos, overrides=None):
    """merge + report, as the CLI chains them."""
    overrides = overrides or build_overrides()
    result = merge(promos, overrides, today=TODAY, validate=validate_promo)
    return construir_informe(
        result.promociones,
        result.avisos,
        cache_dir=tmp_path,
        municipios=MUNICIPIOS,
        today=TODAY,
        version=VERSION,
        overrides=overrides,
    )


def with_registration(promo_id="demo-madrid-uno", **requisitos):
    promo = build_promo(promo_id)
    promo["requisitos"].update({"empadronamiento": dict(REGISTRATION), **requisitos})
    return promo


def review_entry(promo_id="demo-madrid-uno", fields=(INGRESOS,), *, complete=True, candidates=()):
    return {
        "promo_id": promo_id,
        "nombre": "Promoción sintética",
        "operador": "Operador ficticio",
        "municipio": "Madrid",
        "url_oficial": "https://example.org/promo",
        "bases": [{"url": "https://example.org/b.pdf", "titulo": "Bases", "sha256": SHA_A, "es_principal": True}],
        "fuente_sha256": SHA_A,
        "detalle_completo": complete,
        "no_exigidos": [],
        "advertencias": [],
        "campos": [{"campo": f, "motivo": "no_encontrado", "candidatos": list(candidates)} for f in fields],
    }


def informe_of(*entries, stale=(), published=None):
    return {
        "publicadas": [e["promo_id"] for e in entries] if published is None else published,
        "revisiones": list(entries),
        "overrides_desfasados": list(stale),
    }


def pasted_block(body):
    block = re.search(r"```json\n(.*?)\n```", body, re.S).group(1)
    [(promo_id, entry)] = json.loads("{" + block + "}").items()
    return promo_id, entry


# -- acceptance ------------------------------------------------------------------------------


def test_contradicting_values_open_an_issue_showing_both(tmp_path, github, client):
    store(tmp_path, candidate(INGRESOS, 5.5, pagina=2), candidate(INGRESOS, 7.5, pagina=4))
    summary = sync_issues(pipeline_run(tmp_path, [with_registration()]), client)

    assert summary.ok and summary.creados == ["demo-madrid-uno"]
    [issue] = github.open()
    body = issue["body"]
    assert body.startswith("<!-- vpo:review:demo-madrid-uno -->")
    row = next(line for line in body.splitlines() if line.startswith(f"| `{INGRESOS}`"))
    assert "| conflicto |" in row and "**5.5**" in row and "**7.5**" in row
    assert "(https://example.org/bases.pdf#page=2)" in row and "#page=4)" in row
    assert "no superen 7.5 veces el IPREM" in row
    assert "[abrir](https://example.org/promo)" in body
    assert f"https://github.com/{REPO}/edit/main/data/overrides.json" in body
    assert pasted_block(body)[1]["campos"][INGRESOS]["fuente_sha256"] == SHA_A
    assert github.labels == set(ETIQUETAS)


def test_an_override_closes_the_issue_on_the_next_run(tmp_path, github, client):
    promos = [with_registration()]
    sync_issues(pipeline_run(tmp_path, promos), client)
    assert len(github.open()) == 1

    overrides = build_overrides({"demo-madrid-uno": build_entry({INGRESOS: build_field(5.5)})})
    summary = sync_issues(pipeline_run(tmp_path, promos, overrides), client)

    assert summary.cerrados == ["demo-madrid-uno"] and github.open() == []
    assert github.issues[1]["comments"] == ["No quedan campos pendientes."]


def test_a_promotion_leaving_the_list_closes_its_issue(github, client):
    sync_issues(informe_of(review_entry()), client)
    sync_issues(informe_of(), client)
    assert github.open() == [] and "ya no está" in github.issues[1]["comments"][0]


# -- the block to paste ----------------------------------------------------------------------

ALL_POINTERS = (
    "/nombre",
    "/operador/nombre",
    "/ubicacion/municipio",
    "/ubicacion/distrito",
    "/ubicacion/direccion",
    "/ubicacion/municipio_ine",
    "/enlaces/oficial",
    "/enlaces/solicitud",
    "/estado",
    "/regimen",
    "/programa",
    "/modalidad",
    "/viviendas_total",
    "/tipologias",
    INGRESOS,
    "/requisitos/ingresos_min_iprem",
    "/requisitos/ingresos_por_miembros",
    "/requisitos/iprem_pagas",
    "/requisitos/iprem_ejercicio",
    "/requisitos/tasa_esfuerzo_max",
    EMPADRONAMIENTO,
    "/requisitos/edad",
    "/requisitos/no_titular_vivienda",
    "/fechas/inscripcion_inicio",
    "/fechas/inscripcion_fin",
    "/fechas/sorteo",
    "/fechas/entrega_prevista",
)


def overrides_errors(overrides):
    return schema_errors(overrides, "overrides", SCHEMA_DIR)


def test_the_unedited_block_never_validates():
    body = cuerpo_revision(review_entry(fields=ALL_POINTERS), REPO)
    promo_id, entry = pasted_block(body)
    assert list(entry["campos"]) == list(ALL_POINTERS)
    assert overrides_errors(build_overrides({promo_id: entry}))  # the date placeholder

    # Even with the rest filled in, every placeholder value is refused by the merge.
    for correction in entry["campos"].values():
        correction["fecha"] = "2026-11-27"
    overrides = build_overrides({promo_id: entry})
    assert overrides_errors(overrides) == []
    result = merge([build_promo()], overrides, today=TODAY, validate=validate_promo)
    refused = {a.detalle.split(":")[0] for a in result.avisos if a.tipo == "override_invalido"}
    assert refused == set(ALL_POINTERS)


def test_the_edited_block_is_accepted():
    promo_id, entry = pasted_block(cuerpo_revision(review_entry(), REPO))
    entry["campos"][INGRESOS].update(valor=5.5, motivo="Bases p. 2", autor="alguien", fecha="2026-11-27")
    overrides = build_overrides({promo_id: entry})
    assert overrides_errors(overrides) == []
    result = merge([build_promo()], overrides, today=TODAY, validate=validate_promo)
    assert result.avisos == [] and result.promociones[0]["requisitos"]["ingresos_max_iprem"] == 5.5


def test_guidance_to_declare_a_requirement_not_demanded():
    body = cuerpo_revision({**review_entry(fields=(EMPADRONAMIENTO,)), "no_exigidos": ["edad"]}, REPO)
    assert "sustituye la lista entera" in body
    line = body.split("```json\n")[2].split("\n```")[0]
    [(pointer, correction)] = json.loads("{" + line + "}").items()
    assert pointer == "/requisitos/no_exigidos" and correction["valor"] == ["edad", "COMPLETAR"]
    assert "no_exigidos" not in cuerpo_revision(review_entry(fields=("/estado",)), REPO)


# -- untrusted text and size -----------------------------------------------------------------


def test_document_text_is_neutralised():
    nasty = "@octocat ver #12 y GH-3 <!-- vpo:review:otra --> </details> | ``` https://github.com/a/b/issues/1"
    item = {**candidate("/requisitos/otros", nasty, evidencia=nasty).to_dict(), "documento": "javascript:alert(1)"}
    entry = {**review_entry(candidates=[item]), "nombre": nasty, "operador": nasty}
    body = cuerpo_revision(entry, REPO)
    assert re.findall(r"<!-- vpo:(\w+):", body) == ["review", "campos", "detalle"]
    assert "@octocat" not in body and "#12" not in body and "GH-3" not in body
    assert "</details>" not in body and "https://github.com/a/b" not in body and "javascript:" not in body
    fences = [line for line in body.splitlines() if "```" in line]
    assert fences == ["```json", "```"] * 2  # only our JSON blocks
    row = next(line for line in body.splitlines() if line.startswith("| `/"))
    assert len(re.findall(r"(?<!\\)\|", row)) == 4


def test_long_bodies_stay_under_the_limit():
    items = [{**candidate("/tipologias", ["x" * 500] * 20, evidencia="y" * 400).to_dict(), "confianza": 1}]
    items = [{**items[0], "valor": f"{n}" + "z" * 500} for n in range(200)]
    body = cuerpo_revision(review_entry(fields=ALL_POINTERS, candidates=items), REPO)
    assert len(body) <= MAX_CUERPO
    assert pasted_block(body)[0] == "demo-madrid-uno"


# -- updates ---------------------------------------------------------------------------------


def test_an_unchanged_run_writes_nothing(github, client):
    sync_issues(informe_of(review_entry()), client)
    github.calls.clear()
    summary = sync_issues(informe_of(review_entry()), client)
    assert github.writes() == [] and summary.creados == summary.actualizados == []
    assert len(github.issues) == 1


def test_comment_only_when_the_pending_set_changes(github, client):
    sync_issues(informe_of(review_entry(fields=(INGRESOS, EMPADRONAMIENTO))), client)
    renamed = {**review_entry(fields=(INGRESOS, EMPADRONAMIENTO)), "operador": "Otro nombre"}
    sync_issues(informe_of(renamed), client)
    assert "Otro nombre" in github.issues[1]["body"] and github.issues[1]["comments"] == []

    summary = sync_issues(informe_of(review_entry(fields=(INGRESOS,))), client)
    assert summary.comentados == ["demo-madrid-uno"]
    expected = f"Han cambiado los campos pendientes.\n- Resueltos: `{EMPADRONAMIENTO}`\n"
    assert github.issues[1]["comments"] == [expected]


def test_a_run_without_cache_keeps_the_body_with_candidates(github, client):
    detailed = review_entry(candidates=[candidate(INGRESOS, 5.5).to_dict()])
    sync_issues(informe_of(detailed), client)
    body = github.issues[1]["body"]

    sync_issues(informe_of(review_entry(complete=False)), client)
    assert github.issues[1]["body"] == body

    changed = review_entry(fields=(INGRESOS, EMPADRONAMIENTO), complete=False)
    sync_issues(informe_of(changed), client)
    assert EMPADRONAMIENTO in github.issues[1]["body"]


# -- limit and failures ----------------------------------------------------------------------


def test_at_most_twenty_new_issues_and_a_summary_for_the_rest(github, client):
    entries = [review_entry(f"demo-{n:02d}") for n in range(25)]
    summary = sync_issues(informe_of(*entries), client)
    individual = [i for i in github.open() if "<!-- vpo:review:" in i["body"]]
    [overflow] = [i for i in github.open() if "<!-- vpo:summary -->" in i["body"]]
    assert len(individual) == 20 and summary.en_resumen == [f"demo-{n:02d}" for n in range(20, 25)]
    assert "demo-20" in overflow["body"] and "demo-19" not in overflow["body"]
    assert "<!-- vpo:review:" not in overflow["body"]

    summary = sync_issues(informe_of(*entries), client)
    assert len(summary.creados) == 5 and summary.en_resumen == [] and summary.cerrados == ["resumen"]
    assert len(github.open()) == 25


def test_the_summary_is_not_duplicated(github, client):
    entries = [review_entry(f"demo-{n:02d}") for n in range(5)]
    sync_issues(informe_of(*entries), client, max_nuevos=1)
    sync_issues(informe_of(*entries), client, max_nuevos=1)
    assert sum("<!-- vpo:summary -->" in i["body"] for i in github.issues.values()) == 1


def test_one_failing_call_does_not_stop_the_rest(github, client):
    github.fails = lambda command, body: command[1:3] == ["issue", "create"] and "demo-01" in body
    summary = sync_issues(informe_of(*(review_entry(f"demo-{n:02d}") for n in range(3))), client)
    assert summary.creados == ["demo-00", "demo-02"] and not summary.ok
    assert summary.errores[0].startswith("demo-01: ")


def test_nothing_is_created_if_the_list_cannot_be_read(github, client):
    github.fails = lambda command, body: command[1:3] == ["issue", "list"]
    summary = sync_issues(informe_of(review_entry()), client)
    assert github.issues == {} and not summary.ok


def test_a_missing_gh_is_an_error_not_a_crash():
    def runner(command, **kwargs):
        raise FileNotFoundError("gh")

    summary = sync_issues(informe_of(review_entry()), GhClient(REPO, runner=runner))
    assert not summary.ok and summary.creados == []


# -- stale corrections -----------------------------------------------------------------------


def test_stale_override_issue_opens_and_closes(tmp_path, github, client):
    promos = [with_registration()]
    old = build_overrides({"demo-madrid-uno": build_entry({INGRESOS: build_field(5.5, sha=SHA_B)})})
    sync_issues(pipeline_run(tmp_path, promos, old), client)
    [issue] = github.open("override-stale")
    assert "<!-- vpo:stale:demo-madrid-uno -->" in issue["body"]
    assert SHA_B in issue["body"] and f'"fuente_sha256": "{SHA_A}"' in issue["body"]

    sync_issues(pipeline_run(tmp_path, promos, old), client)
    assert len(github.issues) == 1

    new = build_overrides({"demo-madrid-uno": build_entry({INGRESOS: build_field(5.5, sha=SHA_A)})})
    sync_issues(pipeline_run(tmp_path, promos, new), client)
    assert github.open("override-stale") == []


def test_stale_entry_of_a_hidden_promotion(tmp_path, github, client):
    informe = construir_informe(
        [],
        [Aviso("override_desfasado", "oculta", f"la fuente cambió desde la corrección de: {INGRESOS}")],
        cache_dir=tmp_path,
        municipios=MUNICIPIOS,
        today=TODAY,
        version=VERSION,
    )
    assert sync_issues(informe, client).creados == ["oculta"]


# -- source health ---------------------------------------------------------------------------

NOW = datetime(2026, 11, 27, 5, 0, tzinfo=UTC)


def state_of(estado="error", fallos=3, exito="2026-11-20T05:00:00Z", documentos=None):
    info = {
        "estado": estado,
        "ultima_ejecucion": "2026-11-27T05:00:00Z",
        "ultimo_exito": exito,
        "fallos_consecutivos": fallos,
        "ultimo_error": "ListingError: @alguien #3",
        "promociones_vistas": None,
        "duracion_s": 1.0,
    }
    return {"fuentes": {"emvs-madrid": info}, "documentos": documentos or {}}


@pytest.mark.parametrize(
    ("state", "broken"),
    [
        (state_of(fallos=2), False),
        (state_of(fallos=3), True),
        (state_of("degradado", 0, "2026-11-25T05:00:00Z"), False),
        (state_of("degradado", 0, "2026-11-24T05:00:30Z"), True),
        (state_of("degradado", 0, None), False),
        (state_of("degradado", 0, None, {"k": {"fuente_id": "emvs-madrid", "primera_vez": "2026-11-24"}}), True),
        (state_of("degradado", 0, None, {"k": {"fuente_id": "emvs-madrid", "primera_vez": "2026-11-26"}}), False),
        (state_of("ok", 0), False),
    ],
)
def test_when_a_source_counts_as_broken(github, client, state, broken):
    sync_health(state, client, now=NOW)
    assert len(github.open("scraper-broken")) == int(broken)


def test_source_issue_is_updated_and_closed_on_the_first_ok_run(github, client):
    sync_health(state_of(fallos=3), client, now=NOW)
    summary = sync_health(state_of(fallos=4), client, now=NOW)
    [issue] = github.open("scraper-broken")
    assert summary.actualizados == ["emvs-madrid"] and issue["comments"] == []
    assert "<!-- vpo:source:emvs-madrid -->" in issue["body"] and "@alguien" not in issue["body"]

    # Neither broken nor ok: leave it open.
    sync_health(state_of(fallos=1), client, now=NOW)
    assert len(github.open("scraper-broken")) == 1

    assert sync_health(state_of("ok", 0), client, now=NOW).cerrados == ["emvs-madrid"]
    assert github.open("scraper-broken") == []


# -- repository files ------------------------------------------------------------------------


def test_labels_file_and_templates_match_the_code():
    labels = (ROOT / ".github" / "labels.yml").read_text(encoding="utf-8")
    declared = re.findall(r'- name: (\S+)\n  color: "(\w+)"\n  description: "(.*)"', labels)
    assert {name: (color, text) for name, color, text in declared} == ETIQUETAS
    for template in ("correccion-dato", "nueva-fuente"):
        text = (ROOT / ".github" / "ISSUE_TEMPLATE" / f"{template}.yml").read_text(encoding="utf-8")
        assert f'labels: ["{template}"]' in text and "datos personales" in text
    form = (ROOT / ".github" / "ISSUE_TEMPLATE" / "correccion-dato.yml").read_text(encoding="utf-8")
    assert "id: id\n" in form
