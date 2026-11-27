"""Synchronise GitHub Issues with the review report through the ``gh`` CLI (ARCHITECTURE.md §4.1).

Every issue is identified by a hidden marker in its body. Bodies are deterministic (no dates),
so an unchanged situation produces no edit. Text coming from documents or web pages is
untrusted and always goes through ``_texto``, which also makes forging a marker impossible.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import quote

REPO_POR_DEFECTO = "ServerHeaven/vpo-madrid"
MAX_NUEVOS = 20
MAX_CUERPO = 60_000  # GitHub rejects bodies over 65536 characters
FALLOS_PARA_AVISAR = 3
DIAS_DEGRADADA = 3
DIAS_SIN_EJECUCION = 3

REVISION = "needs-review"
DESFASADO = "override-stale"
ROTA = "scraper-broken"
INFRA = "infra"
# name -> (colour, description); mirrored in .github/labels.yml
ETIQUETAS = {
    REVISION: ("FBCA04", "Datos de una promoción pendientes de revisión manual"),
    DESFASADO: ("D93F0B", "La fuente cambió después de una corrección manual"),
    ROTA: ("B60205", "Una fuente del scraper lleva varios días fallando"),
    INFRA: ("5319E7", "El proceso diario no se está ejecutando"),
    "correccion-dato": ("0E8A16", "Aviso de un dato erróneo enviado por una persona"),
    "nueva-fuente": ("1D76DB", "Propuesta de una nueva fuente de promociones"),
}

MARCADOR_RESUMEN = "<!-- vpo:summary -->"
MARCADOR_LATIDO = "<!-- vpo:heartbeat -->"
_CAMPOS = re.compile(r"<!-- vpo:campos:([^ ]*) -->")
_POINTER = re.compile(r"^/[a-z0-9_*]+(?:/[a-z0-9_*]+)*$")
_ZWSP = chr(0x200B)  # zero width space
_UNSAFE_URL = re.compile(r'[\s()<>|`"\\[\]]')

_ANEJO = '`{"disponibilidad": "desconocido", "precio_mensual_eur": null}`'
_FECHA = 'fecha `"AAAA-MM-DD"`'
_FORMATOS = {
    "/estado": "`proxima`, `inscripcion_abierta`, `inscripcion_cerrada`, `sorteo_adjudicacion`, "
    "`lista_espera_abierta` o `finalizada`, entre comillas",
    "/ubicacion/municipio_ine": 'código INE de 5 cifras entre comillas, como `"28079"`',
    "/tipologias": "lista completa (sustituye a la actual); cada elemento con `dormitorios`, "
    "`superficie_util_m2`, `renta_mensual_eur`, `renta_mensual_max_eur`, `num_viviendas`, `garaje`, "
    f"`trastero` y `adaptada_pmr`; lo desconocido es `null` y los anejos desconocidos {_ANEJO}",
    "/requisitos/ingresos_min_iprem": "número de veces el IPREM, como `1.5`",
    "/requisitos/ingresos_max_iprem": "número de veces el IPREM, como `5.5`. Si las bases dan una tabla "
    "por miembros, sustituye la ruta por `/requisitos/ingresos_por_miembros`",
    "/requisitos/ingresos_por_miembros": "lista de objetos con `miembros_desde`, `miembros_hasta`, "
    "`min_iprem` y `max_iprem`",
    "/requisitos/iprem_pagas": "`12` o `14`",
    "/requisitos/iprem_ejercicio": "año, como `2025`",
    "/requisitos/tasa_esfuerzo_max": "fracción, como `0.35`",
    "/requisitos/empadronamiento": 'objeto con `ambito` (`"municipio"` o `"comunidad"`), `municipio_ine` '
    "(`null` si el ámbito es la comunidad), `anios_min` (`0` si no se pide antigüedad), `ininterrumpido` y "
    "`alternativa_trabajo`",
    "/requisitos/edad": 'objeto con `min`, `max` y `tipo` (`"requisito"` o `"cupo"`)',
    "/fechas/inscripcion_inicio": _FECHA,
    "/fechas/inscripcion_fin": _FECHA,
    "/fechas/sorteo": _FECHA,
    "/fechas/entrega_prevista": '`"2027"`, `"2027-T2"` o `"2027-06"`',
}
# Requirements that requisitos.no_exigidos accepts.
_NO_EXIGIBLES = (
    "ingresos_min_iprem",
    "ingresos_max_iprem",
    "tasa_esfuerzo_max",
    "empadronamiento",
    "edad",
    "no_titular_vivienda",
)


def repositorio() -> str:
    return os.environ.get("GITHUB_REPOSITORY") or REPO_POR_DEFECTO


class GhError(RuntimeError):
    """A gh call failed."""


@dataclass(frozen=True)
class Issue:
    numero: int
    titulo: str
    cuerpo: str


class GhClient:
    """Thin wrapper of ``gh``. Never uses a shell; bodies travel through stdin."""

    def __init__(self, repo: str, runner: Callable[..., Any] = subprocess.run) -> None:
        self.repo = repo
        self._runner = runner

    def _run(self, *args: str, body: str | None = None) -> str:
        command = ["gh", *args, "--repo", self.repo]
        try:
            done = self._runner(
                command,
                input=body,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise GhError(f"gh {args[0]} {args[1]}: {error}") from error
        if done.returncode != 0:
            raise GhError(f"gh {args[0]} {args[1]}: {(done.stderr or '').strip()[:300]}")
        return done.stdout or ""

    def ensure_label(self, name: str, color: str, description: str) -> None:
        self._run("label", "create", name, "--color", color, "--description", description, "--force")

    def list_open(self, label: str) -> list[Issue]:
        query = ("--state", "open", "--limit", "1000", "--json", "number,title,body")
        out = self._run("issue", "list", "--label", label, *query)
        try:
            rows = json.loads(out or "[]")
            found = [
                Issue(row["number"], row["title"], (row["body"] or "").replace("\r\n", "\n")) for row in rows
            ]
        except (ValueError, KeyError, TypeError) as error:
            raise GhError(f"gh issue list: respuesta ilegible ({error})") from error
        return sorted(found, key=lambda issue: issue.numero)

    def create(self, title: str, body: str, label: str) -> None:
        self._run("issue", "create", f"--title={title}", "--label", label, "--body-file", "-", body=body)

    def edit(self, number: int, title: str, body: str) -> None:
        self._run("issue", "edit", str(number), f"--title={title}", "--body-file", "-", body=body)

    def comment(self, number: int, body: str) -> None:
        self._run("issue", "comment", str(number), "--body-file", "-", body=body)

    def close(self, number: int, comment: str) -> None:
        # Close first: if closing keeps failing, no comment piles up every day.
        self._run("issue", "close", str(number))
        self.comment(number, comment)


@dataclass
class Resumen:
    """What one synchronisation did. Entries are promotion or source ids."""

    creados: list[str] = field(default_factory=list)
    actualizados: list[str] = field(default_factory=list)
    comentados: list[str] = field(default_factory=list)
    cerrados: list[str] = field(default_factory=list)
    en_resumen: list[str] = field(default_factory=list)  # over the limit of new issues
    errores: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errores


# -- untrusted text -------------------------------------------------------------------------


def _inerte(text: str) -> str:
    """Break @mentions, #123, GH-123 and URL autolinks with a zero width space."""
    text = text.replace("@", "@" + _ZWSP).replace("#", "#" + _ZWSP)
    text = re.sub(r"(?i)\b(gh)-(?=\d)", rf"\1{_ZWSP}-", text)
    return text.replace("://", f":{_ZWSP}//").replace("www.", f"www{_ZWSP}.")


def _texto(value: Any, limit: int = 300) -> str:
    """One line of inert Markdown: no HTML, comments, tables, code or references."""
    text = " ".join(str(value).replace(_ZWSP, "").split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    text = re.sub(r"([\\`*_\[\]|~$])", r"\\\1", text)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return _inerte(text)


def _titulo(text: str) -> str:
    return _inerte(" ".join(text.split()))[:200].strip()


def _enlace(label: str, url: str | None, pagina: int | None = None) -> str:
    """A Markdown link to an http(s) URL; ``label`` is already safe."""
    if not url or not url.lower().startswith(("http://", "https://")):
        return label
    if pagina:
        url = f"{url.partition('#')[0]}#page={pagina}"
    return f"[{label}]({_UNSAFE_URL.sub(lambda m: quote(m.group(), safe=''), url)})"


# -- bodies ---------------------------------------------------------------------------------


def _marcador(tipo: str, clave: str) -> str:
    return f"<!-- vpo:{tipo}:{clave} -->"


def _marcador_campos(pointers: list[str]) -> str:
    return f"<!-- vpo:campos:{','.join(p for p in pointers if _POINTER.match(p))} -->"


def _campos_de(body: str) -> list[str] | None:
    match = _CAMPOS.search(body)
    return None if match is None else sorted(p for p in match.group(1).split(",") if p)


def _enlace_editar(repo: str) -> str:
    return f"[Editar `data/overrides.json`](https://github.com/{repo}/edit/main/data/overrides.json)"


def _valor_inicial(pointer: str) -> Any:
    """A placeholder that no schema accepts, so an unedited block cannot be merged."""
    non_text = pointer.startswith(("/requisitos", "/fechas", "/tipologias")) or pointer in (
        "/estado",
        "/regimen",
        "/programa",
        "/modalidad",
        "/viviendas_total",
        "/ubicacion/municipio_ine",
    )
    # Free-text fields would accept the string "COMPLETAR": give them an object instead.
    return "COMPLETAR" if non_text else {"COMPLETAR": None}


def _correccion(pointer: str, sha256: str | None, valor: Any = None) -> dict[str, Any]:
    return {
        "valor": _valor_inicial(pointer) if valor is None else valor,
        "motivo": "COMPLETAR: página y apartado de las bases",
        "autor": "COMPLETAR",
        "fecha": "AAAA-MM-DD",  # not a date on purpose
        "fuente_sha256": sha256,
    }


def _fragmento(key: str, value: Any) -> str:
    """'"key": {...}' ready to paste inside an object."""
    lines = json.dumps({key: value}, ensure_ascii=False, indent=2).splitlines()[1:-1]
    return "\n".join(line[2:] for line in lines)


def _candidatos(candidates: list[dict[str, Any]], limit: int) -> str:
    if not candidates:
        return "—"
    # One of each distinct value first, so a conflict always shows its sides.
    seen: set[str] = set()
    first, rest = [], []
    for item in candidates:
        key = json.dumps(item["valor"], ensure_ascii=False, sort_keys=True)
        (rest if key in seen else first).append((key, item))
        seen.add(key)
    ordered = [*first, *rest]
    lines = []
    for key, item in ordered[:limit]:
        page = item["pagina"]
        where = _enlace(f"p. {page}", item["documento"], page) if page else _enlace("documento", item["documento"])
        lines.append(f"**{_texto(key, 200)}** · {where} · «{_texto(item['evidencia'], 250)}»")
    if len(ordered) > limit:
        lines.append(f"(y {len(ordered) - limit} más)")
    return "<br>".join(lines)


def _guia_no_exigidos(entry: dict[str, Any], pointers: list[str]) -> list[str]:
    names = [p.removeprefix("/requisitos/") for p in pointers if p.startswith("/requisitos/")]
    names = [name for name in names if name in _NO_EXIGIBLES]
    if not names:
        return []
    current = entry["no_exigidos"]
    line = _fragmento(
        "/requisitos/no_exigidos",
        _correccion("/requisitos/no_exigidos", entry["fuente_sha256"], [*current, "COMPLETAR"]),
    )
    return [
        "",
        "**Si las bases dicen que un requisito no se exige**, no rellenes su campo: borra su entrada (si hoy "
        'tiene un valor incompleto, déjala con `"valor": null`) y añade dentro de `"campos"` la ruta '
        "`/requisitos/no_exigidos`. Su `valor` **sustituye la lista entera** "
        f"(ahora: `{json.dumps(current)}`), así que conserva lo que ya tenga y cambia `COMPLETAR` por "
        f"{' o '.join(f'`{json.dumps(n)}`' for n in names)}:",
        "",
        "```json",
        line,
        "```",
    ]


def _cuerpo_revision(entry: dict[str, Any], repo: str, limit: int) -> str:
    pointers = [item["campo"] for item in entry["campos"]]
    detail = "completo" if entry["detalle_completo"] else "parcial"
    lines = [
        _marcador("review", entry["promo_id"]),
        _marcador_campos(pointers),
        f"<!-- vpo:detalle:{detail}:{entry['fuente_sha256'] or '-'} -->",
        "",
        "Faltan datos de esta promoción o las bases se contradicen. Mientras tanto la web no los muestra.",
        "",
        f"- **Promoción:** {_texto(entry['nombre'])} (`{entry['promo_id']}`)",
        f"- **Operador:** {_texto(entry['operador'])}",
        f"- **Municipio:** {_texto(entry['municipio'])}",
        f"- **Ficha oficial:** {_enlace('abrir', entry['url_oficial'])}",
    ]
    pages = [c for item in entry["campos"] for c in item["candidatos"] if c["pagina"]]
    for document in entry["bases"]:
        page = next((c["pagina"] for c in pages if c["documento"] == document["url"]), 1)
        kind = "Bases (principal)" if document["es_principal"] else "Documento"
        lines.append(f"- **{kind}:** {_enlace(_texto(document['titulo'], 150), document['url'], page)}")

    lines += ["", "### Campos pendientes", "", "| campo | motivo | candidatos con página y fragmento |"]
    lines.append("|---|---|---|")
    for item in entry["campos"]:
        # Reason codes are our own constants (MOTIVOS plus "no_disponible").
        lines.append(f"| `{item['campo']}` | {item['motivo']} | {_candidatos(item['candidatos'], limit)} |")

    block = {
        "campos": {p: _correccion(p, entry["fuente_sha256"]) for p in pointers},
        "ocultar": False,
        "nota_publica": None,
    }
    lines += [
        "",
        "### Cómo corregirlo",
        "",
        '1. Comprueba el dato en las bases y pega este bloque dentro de `"overrides"` (con una coma si ya '
        'hay otras entradas). Si la promoción ya está, añade solo las rutas dentro de su `"campos"`.',
        '2. Sustituye cada `COMPLETAR`, escribe en `autor` tu usuario de GitHub (sin arroba) y en `fecha` '
        "el día de hoy como `AAAA-MM-DD`. Borra las rutas que no vayas a rellenar: sin editar, el bloque "
        "no pasa la validación.",
        "",
        "```json",
        _fragmento(entry["promo_id"], block),
        "```",
        "",
        "Formato de cada `valor`:",
        "",
    ]
    lines += [f"- `{p}`: {_FORMATOS.get(p, 'según el schema de la promoción')}" for p in pointers]
    lines += _guia_no_exigidos(entry, pointers)
    lines += ["", _enlace_editar(repo)]
    return "\n".join(lines) + "\n"


def cuerpo_revision(entry: dict[str, Any], repo: str) -> str:
    """Body of a review issue, showing fewer candidates if it would be too long."""
    for limit in (10, 5, 2, 1, 0):
        body = _cuerpo_revision(entry, repo, limit)
        if len(body) <= MAX_CUERPO:
            return body
    return body[:MAX_CUERPO]  # markers are at the top, so they survive


def cuerpo_desfasado(entry: dict[str, Any], repo: str) -> str:
    pointers = [item["campo"] for item in entry["campos"]]
    current = entry["sha256_actual"]
    lines = [
        _marcador("stale", entry["promo_id"]),
        _marcador_campos(pointers),
        "",
        "La fuente cambió desde que se hizo una corrección manual. La corrección **se sigue aplicando**: "
        "comprueba que todavía es válida.",
        "",
        f"- **Promoción:** {_texto(entry['nombre'])} (`{entry['promo_id']}`)",
        f"- **Ficha oficial:** {_enlace('abrir', entry['url_oficial'])}",
        f"- **Bases actuales:** {_enlace('abrir', entry['url_bases'], 1)}",
        "",
        "| campo corregido | sha256 al corregir |",
        "|---|---|",
    ]
    for item in entry["campos"]:
        old = item["sha256_anterior"]
        lines.append(f"| `{item['campo']}` | {f'`{old}`' if old else '—'} |")
    lines += ["", "Cuando lo hayas revisado, actualiza `fuente_sha256` en esas rutas."]
    if current:
        lines += ["Valor actual:", "", "```json", f'"fuente_sha256": "{current}"', "```"]
    else:
        lines.append("Ahora no hay un documento de bases principal.")
    lines += ["", _enlace_editar(repo)]
    return "\n".join(lines)[:MAX_CUERPO] + "\n"


def cuerpo_fuente(fuente_id: str, info: dict[str, Any]) -> str:
    lines = [
        _marcador("source", fuente_id),
        "",
        f"La fuente `{fuente_id}` no se está leyendo bien. Se conservan los últimos datos correctos.",
        "",
        f"- **Estado:** {_texto(info['estado'])}",
        f"- **Fallos consecutivos:** {info['fallos_consecutivos']}",
        f"- **Última ejecución correcta:** {_texto(info['ultimo_exito'] or 'ninguna')}",
        f"- **Último error:** {_texto(info['ultimo_error'] or 'sin detalle', 600)}",
        "",
        "Este aviso se cierra solo en la primera ejecución correcta.",
    ]
    return "\n".join(lines) + "\n"


def cuerpo_latido(ultima: str | None) -> str:
    lines = [
        MARCADOR_LATIDO,
        "",
        f"Hace más de {DIAS_SIN_EJECUCION} días que no se completa una lectura de las fuentes. "
        "Los datos de la web pueden estar desactualizados.",
        "",
        f"- **Última ejecución:** {_texto(ultima or 'ninguna')}",
        "",
        "Revisa en la pestaña *Actions* que el workflow `scrape` esté activado, que su programación "
        "(`schedule`) no esté comentada y que sus últimas ejecuciones no hayan fallado.",
        "",
        "Este aviso se cierra solo en la siguiente ejecución completa.",
    ]
    return "\n".join(lines) + "\n"


def _cuerpo_resumen(excess: list[tuple[str, str]]) -> str:
    lines = [
        MARCADOR_RESUMEN,
        "",
        f"Quedan {len(excess)} avisos sin issue propio (se abren como máximo {MAX_NUEVOS} por ejecución). "
        "Se irán creando en las siguientes.",
        "",
    ]
    size = sum(len(line) + 1 for line in lines)
    for position, (_, line) in enumerate(excess):
        if size + len(line) > MAX_CUERPO:
            lines.append(f"(y {len(excess) - position} más)")
            break
        lines.append(line)
        size += len(line) + 1
    return "\n".join(lines) + "\n"


# -- synchronisation ------------------------------------------------------------------------


@dataclass(frozen=True)
class _Deseado:
    """An issue that should be open."""

    clave: str
    titulo: str
    cuerpo: str
    linea: str = ""  # its line in the summary issue
    detalle_completo: bool = True
    sha256: str | None = None


def _intentar(resumen: Resumen, clave: str, action: Callable[[], Any]) -> bool:
    """Run one gh operation; a failure is recorded and does not stop the others."""
    try:
        action()
    except GhError as error:
        resumen.errores.append(f"{clave}: {error}")
        return False
    return True


def _listar(gh: GhClient, label: str, resumen: Resumen) -> list[Issue] | None:
    """None if the list could not be read: then nothing is created, to avoid duplicates."""
    try:
        return gh.list_open(label)
    except GhError as error:
        resumen.errores.append(f"{label}: {error}")
        return None


def _por_clave(issues: list[Issue], tipo: str) -> dict[str, list[Issue]]:
    pattern = re.compile(rf"<!-- vpo:{tipo}:([a-z0-9-]+) -->")
    found: dict[str, list[Issue]] = {}
    for issue in issues:
        if match := pattern.search(issue.cuerpo):
            found.setdefault(match.group(1), []).append(issue)
    return found


def _comentario_cambios(before: list[str], after: list[str]) -> str:
    lines = ["Han cambiado los campos pendientes."]
    for label, pointers in (("Nuevos", set(after) - set(before)), ("Resueltos", set(before) - set(after))):
        if pointers:
            lines.append(f"- {label}: {', '.join(f'`{p}`' for p in sorted(pointers) if _POINTER.match(p))}")
    return "\n".join(lines) + "\n"


def _actualizar(gh: GhClient, issue: Issue, wanted: _Deseado, resumen: Resumen) -> None:
    if issue.titulo == wanted.titulo and issue.cuerpo.rstrip() == wanted.cuerpo.rstrip():
        return
    before, after = _campos_de(issue.cuerpo), _campos_de(wanted.cuerpo)
    # Without the extraction cache, keep the body that still shows the candidates.
    had_detail = f"<!-- vpo:detalle:completo:{wanted.sha256 or '-'} -->" in issue.cuerpo
    if not wanted.detalle_completo and had_detail and before == after:
        return
    if not _intentar(resumen, wanted.clave, lambda: gh.edit(issue.numero, wanted.titulo, wanted.cuerpo)):
        return
    resumen.actualizados.append(wanted.clave)
    if before is None or after is None or before == after:
        return
    if _intentar(resumen, wanted.clave, lambda: gh.comment(issue.numero, _comentario_cambios(before, after))):
        resumen.comentados.append(wanted.clave)


def _cerrar(gh: GhClient, issues: list[Issue], clave: str, comment: str, resumen: Resumen) -> None:
    for issue in issues:
        if _intentar(resumen, clave, lambda number=issue.numero: gh.close(number, comment)):
            resumen.cerrados.append(clave)


def _revision(entry: dict[str, Any], repo: str) -> _Deseado:
    fields = ", ".join(f"`{item['campo']}`" for item in entry["campos"])
    return _Deseado(
        clave=entry["promo_id"],
        titulo=_titulo(f"Revisar datos: {entry['nombre']} ({entry['municipio']})"),
        cuerpo=cuerpo_revision(entry, repo),
        linea=f"- {_texto(entry['nombre'], 150)} (`{entry['promo_id']}`), pendiente: {fields}",
        detalle_completo=entry["detalle_completo"],
        sha256=entry["fuente_sha256"],
    )


def _desfasado(entry: dict[str, Any], repo: str) -> _Deseado:
    fields = ", ".join(f"`{item['campo']}`" for item in entry["campos"])
    return _Deseado(
        clave=entry["promo_id"],
        titulo=_titulo(f"Corrección desfasada: {entry['nombre']}"),
        cuerpo=cuerpo_desfasado(entry, repo),
        linea=f"- {_texto(entry['nombre'], 150)} (`{entry['promo_id']}`), corrección desfasada: {fields}",
    )


def _sync_resumen(gh: GhClient, issues: list[Issue], excess: list[tuple[str, str]], resumen: Resumen) -> None:
    existing = [issue for issue in issues if MARCADOR_RESUMEN in issue.cuerpo]
    if not excess:
        _cerrar(gh, existing, "resumen", "Todos los avisos tienen ya su propio issue.", resumen)
        return
    title = "Revisiones pendientes sin issue propio"
    body = _cuerpo_resumen(excess)
    if not existing:
        if _intentar(resumen, "resumen", lambda: gh.create(title, body, REVISION)):
            resumen.creados.append("resumen")
    elif existing[0].cuerpo.rstrip() != body.rstrip():
        if _intentar(resumen, "resumen", lambda: gh.edit(existing[0].numero, title, body)):
            resumen.actualizados.append("resumen")


def sync_issues(informe: dict[str, Any], gh: GhClient, *, max_nuevos: int = MAX_NUEVOS) -> Resumen:
    """Create, update and close the review and stale-override issues.

    At most ``max_nuevos`` issues are created; the rest are listed in one summary issue.
    """
    resumen = Resumen()
    for name, (color, description) in ETIQUETAS.items():
        _intentar(resumen, name, lambda n=name, c=color, d=description: gh.ensure_label(n, c, d))

    published = set(informe["publicadas"])
    groups = (
        # Stale corrections first: they may be publishing wrong data.
        (
            DESFASADO,
            "stale",
            [_desfasado(entry, gh.repo) for entry in informe["overrides_desfasados"]],
            lambda clave: "La corrección ya no está desfasada.",
        ),
        (
            REVISION,
            "review",
            [_revision(entry, gh.repo) for entry in informe["revisiones"]],
            lambda clave: "No quedan campos pendientes."
            if clave in published
            else "La promoción ya no está en la lista publicada.",
        ),
    )

    budget = max_nuevos
    excess: list[tuple[str, str]] = []
    review_issues: list[Issue] | None = None
    for label, kind, wanted_list, closing in groups:
        issues = _listar(gh, label, resumen)
        if issues is None:
            continue
        if label == REVISION:
            review_issues = issues
        existing = _por_clave(issues, kind)
        wanted_keys = {wanted.clave for wanted in wanted_list}
        for key in sorted(existing.keys() - wanted_keys):
            _cerrar(gh, existing[key], key, closing(key), resumen)
        for wanted in wanted_list:
            if wanted.clave in existing:
                _actualizar(gh, existing[wanted.clave][0], wanted, resumen)
            elif budget > 0:
                budget -= 1  # failed attempts count too: do not hammer a broken API
                create = lambda w=wanted, tag=label: gh.create(w.titulo, w.cuerpo, tag)  # noqa: E731
                if _intentar(resumen, wanted.clave, create):
                    resumen.creados.append(wanted.clave)
            else:
                excess.append((wanted.clave, wanted.linea))
                resumen.en_resumen.append(wanted.clave)

    if review_issues is not None:
        _sync_resumen(gh, review_issues, excess, resumen)
    return resumen


def _rota(fuente_id: str, info: dict[str, Any], state: dict[str, Any], today: date) -> bool:
    if info["fallos_consecutivos"] >= FALLOS_PARA_AVISAR:
        return True
    if info["estado"] != "degradado":
        return False
    if info["ultimo_exito"]:
        since = datetime.fromisoformat(info["ultimo_exito"]).date()
    else:
        # Never succeeded: count from the first page ever recorded for this source.
        first = [d["primera_vez"] for d in state.get("documentos", {}).values() if d["fuente_id"] == fuente_id]
        if not first:
            return False
        since = date.fromisoformat(min(first))
    return (today - since).days >= DIAS_DEGRADADA


def _parado(state: dict[str, Any], now: datetime) -> bool:
    """True if no run has finished in the last DIAS_SIN_EJECUCION days."""
    last = state.get("ultima_ejecucion")
    return last is None or now - datetime.fromisoformat(last) > timedelta(days=DIAS_SIN_EJECUCION)


def _latidos_abiertos(gh: GhClient, resumen: Resumen) -> list[Issue] | None:
    color, description = ETIQUETAS[INFRA]
    _intentar(resumen, INFRA, lambda: gh.ensure_label(INFRA, color, description))
    issues = _listar(gh, INFRA, resumen)
    return None if issues is None else [issue for issue in issues if MARCADOR_LATIDO in issue.cuerpo]


def sync_heartbeat(state: dict[str, Any], gh: GhClient, *, now: datetime) -> Resumen:
    """The weekly check: one "infra" issue while the daily run is not happening."""
    resumen = Resumen()
    existing = _latidos_abiertos(gh, resumen)
    if existing is None:
        return resumen
    if not _parado(state, now):
        _cerrar(gh, existing, "heartbeat", "Las fuentes vuelven a leerse.", resumen)
        return resumen
    title = "El proceso diario no se está ejecutando"
    wanted = _Deseado("heartbeat", title, cuerpo_latido(state.get("ultima_ejecucion")))
    if existing:
        _actualizar(gh, existing[0], wanted, resumen)
    elif _intentar(resumen, "heartbeat", lambda: gh.create(title, wanted.cuerpo, INFRA)):
        resumen.creados.append("heartbeat")
    return resumen


def sync_health(state: dict[str, Any], gh: GhClient, *, now: datetime) -> Resumen:
    """One scraper-broken issue per failing source, closed on its first ok run.

    It also closes the heartbeat issue after a recent run; only the weekly check opens it.
    """
    resumen = Resumen()
    if not _parado(state, now) and (stalled := _latidos_abiertos(gh, resumen)):
        _cerrar(gh, stalled, "heartbeat", "Las fuentes vuelven a leerse.", resumen)
    color, description = ETIQUETAS[ROTA]
    _intentar(resumen, ROTA, lambda: gh.ensure_label(ROTA, color, description))
    issues = _listar(gh, ROTA, resumen)
    if issues is None:
        return resumen
    existing = _por_clave(issues, "source")

    for source_id, info in sorted(state["fuentes"].items()):
        mine = existing.get(source_id, [])
        if info["estado"] == "ok":
            _cerrar(gh, mine, source_id, "La fuente ha vuelto a funcionar.", resumen)
        elif _rota(source_id, info, state, now.date()):
            wanted = _Deseado(source_id, f"Fuente rota: {source_id}", cuerpo_fuente(source_id, info))
            if mine:
                _actualizar(gh, mine[0], wanted, resumen)
            elif _intentar(resumen, source_id, lambda w=wanted: gh.create(w.titulo, w.cuerpo, ROTA)):
                resumen.creados.append(source_id)
    return resumen
