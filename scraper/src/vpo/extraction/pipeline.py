"""Runs the extractors and resolves their candidates, field by field (ARCHITECTURE.md §5.1).

Extractors only emit candidates. Everything that decides what is accepted lives here, and the
outcome does not depend on the order in which candidates arrive.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from . import validators
from .base import (
    CAMPOS_ACUMULATIVOS,
    Descarte,
    Document,
    ExtractionContext,
    ExtractionResult,
    Extractor,
    FieldResult,
    plegar,
)

UMBRAL_POR_DEFECTO = 0.8
UMBRALES: dict[str, float] = {}  # per-field overrides of UMBRAL_POR_DEFECTO
UMBRAL_CONFLICTO = 0.5  # from this confidence on, a different value contradicts
MARGEN_PENALIZACION = 0.05  # how far below the threshold an incoherent rent table is left

CAMPOS_CLAVE_ESCANEADO = (
    "/requisitos/ingresos_max_iprem",
    "/requisitos/empadronamiento",
    "/tipologias",
)

_NO_EXIGIDOS = "/requisitos/no_exigidos"
_TIPOLOGIAS = "/tipologias"
_POR_MIEMBROS = "/requisitos/ingresos_por_miembros"
_ORDEN_METODO = {"html": 0, "pdf_tabla": 1, "pdf_texto": 2, "llm": 3}


def extraer(
    doc: Document, ctx: ExtractionContext, extractores: Sequence[Extractor] | None = None
) -> ExtractionResult:
    """Preprocess an unprepared document, run the extractors and resolve."""
    if not doc.necesita_ocr:
        from .preprocess import preparar

        doc = preparar(doc)
    if doc.necesita_ocr:
        return resolver([], ctx, necesita_ocr=True)
    candidatos, advertencias = extraer_candidatos(doc, ctx, extractores)
    return resolver(candidatos, ctx, advertencias=advertencias)


def extraer_candidatos(
    doc_preparado: Document, ctx: ExtractionContext, extractores: Sequence[Extractor] | None = None
) -> tuple[list[FieldResult], list[str]]:
    """(candidates, warnings). A failing extractor loses its own candidates only."""
    if doc_preparado.necesita_ocr:
        return [], []
    if extractores is None:
        from .rules.registry import EXTRACTORES

        extractores = EXTRACTORES

    candidatos: list[FieldResult] = []
    advertencias: list[str] = []
    for extractor in extractores:
        try:
            found = [
                c if c.documento else replace(c, documento=doc_preparado.url)
                for c in extractor.extract(doc_preparado, ctx)
            ]
        except Exception as error:  # noqa: BLE001 - one broken rule must not abort the document
            nombre = getattr(extractor, "nombre", type(extractor).__name__)
            advertencias.append(
                f"El extractor {nombre} ha fallado en {doc_preparado.url}: {type(error).__name__}: {error}"
            )
            continue
        candidatos += found
    return candidatos, advertencias


def resolver(
    candidatos: Iterable[FieldResult],
    ctx: ExtractionContext,
    *,
    necesita_ocr: bool = False,
    advertencias: Iterable[str] = (),
    umbrales: Mapping[str, float] | None = None,
) -> ExtractionResult:
    """Accept at most one value per field (one per distinct value in accumulative fields).

    Candidates may come from several documents.
    """
    umbrales = UMBRALES if umbrales is None else umbrales
    avisos = list(advertencias)

    validos: dict[str, list[FieldResult]] = {}
    implausibles: dict[str, list[FieldResult]] = {}
    for candidato in sorted(candidatos, key=_orden):
        campo = candidato.campo
        if campo not in validators.CAMPOS_SOPORTADOS:
            avisos.append(f"Campo no admitido, se ignora: {campo} ({candidato.regla})")
        elif validators.es_plausible(campo, candidato.valor, ctx.fecha_ref):
            validos.setdefault(campo, []).append(candidato)
        else:
            implausibles.setdefault(campo, []).append(candidato)
            avisos.append(f"Valor fuera de rango en {campo} ({candidato.regla}), se descarta")

    if _TIPOLOGIAS in validos:
        umbral = umbrales.get(_TIPOLOGIAS, UMBRAL_POR_DEFECTO)
        validos[_TIPOLOGIAS] = [_penalizar_incoherente(c, umbral, avisos) for c in validos[_TIPOLOGIAS]]

    aceptados: dict[str, list[FieldResult]] = {}
    descartes: dict[str, Descarte] = {}
    for campo, propios in validos.items():
        umbral = umbrales.get(campo, UMBRAL_POR_DEFECTO)
        if campo in CAMPOS_ACUMULATIVOS:
            elegidos = [c for c in _agrupar(campo, propios) if _alcanza(c, umbral)]
            if elegidos:
                aceptados[campo] = elegidos
            continue
        if campo == _TIPOLOGIAS:
            # A readable table outranks running text, even if the table ends up rejected.
            tablas = [c for c in propios if c.metodo == "pdf_tabla"]
            if any(_alcanza(c, UMBRAL_CONFLICTO) for c in tablas):
                propios = tablas
        grupos = _agrupar(campo, propios)
        rivales = [c for c in grupos if _alcanza(c, UMBRAL_CONFLICTO)]
        if len(rivales) > 1:
            descartes[campo] = Descarte(campo, "conflicto", tuple(rivales))
            continue
        mejor = max(grupos, key=lambda c: c.confianza)  # first wins a tie: grupos is ordered
        if _alcanza(mejor, umbral):
            aceptados[campo] = [mejor]
        else:  # seen, but not clearly enough
            descartes[campo] = Descarte(campo, "no_encontrado", tuple(grupos))

    for campo, propios in implausibles.items():
        if campo not in aceptados and campo not in descartes and campo not in CAMPOS_ACUMULATIVOS:
            descartes[campo] = Descarte(campo, "fuera_de_rango", tuple(propios))

    _coherencia_par(aceptados, descartes, "/fechas/inscripcion_inicio", "/fechas/inscripcion_fin",
                    validators.fechas_coherentes)
    _coherencia_par(aceptados, descartes, "/requisitos/ingresos_min_iprem", "/requisitos/ingresos_max_iprem",
                    validators.ingresos_coherentes)
    _contradicciones_no_exigidos(aceptados, descartes, validos)

    if necesita_ocr:
        _marcar_escaneado(aceptados, descartes)

    campos = sorted((c for propios in aceptados.values() for c in propios), key=_orden)
    return ExtractionResult(
        campos=tuple(campos),
        descartes=tuple(descartes[campo] for campo in sorted(descartes)),
        advertencias=tuple(avisos),
        necesita_ocr=necesita_ocr,
    )


# -- grouping ----------------------------------------------------------------------------------


def _normalizar(valor: Any) -> Any:
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, dict):
        return {k: _normalizar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_normalizar(v) for v in valor]
    return valor


def _json(valor: Any) -> str:
    return json.dumps(_normalizar(valor), sort_keys=True, ensure_ascii=False, default=repr)


def _clave(campo: str, valor: Any) -> str:
    """Two candidates with the same key state the same thing."""
    if campo == "/requisitos/otros" and isinstance(valor, str):
        return " ".join(plegar(valor).split()).rstrip(" .")
    if campo == _TIPOLOGIAS and isinstance(valor, list):
        return _json(sorted(map(_json, valor)))
    return _json(valor)


def _orden(c: FieldResult) -> tuple:
    """Total order of candidates: by field and value, then best first."""
    return (
        c.campo,
        _clave(c.campo, c.valor),
        -c.confianza,
        _ORDEN_METODO.get(c.metodo, len(_ORDEN_METODO)),
        c.documento or "",
        c.pagina or 0,
        c.regla,
        c.evidencia,
        _json(c.valor),
    )


def _agrupar(campo: str, candidatos: Sequence[FieldResult]) -> list[FieldResult]:
    """The best candidate of each distinct value, ordered by value."""
    grupos: dict[str, FieldResult] = {}
    for candidato in sorted(candidatos, key=_orden):
        grupos.setdefault(_clave(campo, candidato.valor), candidato)
    return list(grupos.values())


def _alcanza(candidato: FieldResult, umbral: float) -> bool:
    return round(candidato.confianza, 4) >= umbral


# -- coherence ---------------------------------------------------------------------------------


def _penalizar_incoherente(candidato: FieldResult, umbral: float, avisos: list[str]) -> FieldResult:
    if validators.rentas_coherentes(candidato.valor):
        return candidato
    avisos.append(
        f"Rentas incoherentes en {candidato.documento} ({candidato.regla}): "
        "3 dormitorios más barato que 1 dormitorio"
    )
    return replace(candidato, confianza=round(min(candidato.confianza, umbral - MARGEN_PENALIZACION), 4))


def _coherencia_par(aceptados, descartes, menor: str, mayor: str, coherentes) -> None:
    if menor not in aceptados or mayor not in aceptados:
        return
    a, b = aceptados[menor][0], aceptados[mayor][0]
    if coherentes(a.valor, b.valor):
        return
    for campo in (menor, mayor):
        del aceptados[campo]
        descartes[campo] = Descarte(campo, "conflicto", (a, b))


def _contradicciones_no_exigidos(
    aceptados: dict[str, list[FieldResult]],
    descartes: dict[str, Descarte],
    validos: Mapping[str, Sequence[FieldResult]],
) -> None:
    """A value both found and declared as not required: neither is kept."""
    negaciones = {c.valor: c for c in _agrupar(_NO_EXIGIDOS, validos.get(_NO_EXIGIDOS, ()))}
    retirar: set[str] = set()
    for nombre, negacion in negaciones.items():
        if not _alcanza(negacion, UMBRAL_CONFLICTO):
            continue
        campo = f"/requisitos/{nombre}"
        vistos = [c for c in validos.get(campo, ()) if _alcanza(c, UMBRAL_CONFLICTO)]
        afectados = {campo: vistos}
        borde = validators.BORDES_POR_MIEMBROS.get(nombre)
        if borde is not None:
            afectados[_POR_MIEMBROS] = [
                c
                for c in validos.get(_POR_MIEMBROS, ())
                if _alcanza(c, UMBRAL_CONFLICTO) and any(t[borde] is not None for t in c.valor)
            ]
        for afectado, propios in afectados.items():
            if not propios:
                continue
            retirar.add(nombre)
            aceptados.pop(afectado, None)
            previos = descartes[afectado].candidatos if afectado in descartes else ()
            candidatos = [*_agrupar(afectado, [*previos, *propios]), negacion]
            descartes[afectado] = Descarte(afectado, "conflicto", tuple(candidatos))
    if retirar and _NO_EXIGIDOS in aceptados:
        quedan = [c for c in aceptados.pop(_NO_EXIGIDOS) if c.valor not in retirar]
        if quedan:
            aceptados[_NO_EXIGIDOS] = quedan


def _marcar_escaneado(aceptados: Mapping[str, list[FieldResult]], descartes: dict[str, Descarte]) -> None:
    negados = {f"/requisitos/{c.valor}" for c in aceptados.get(_NO_EXIGIDOS, ())}
    for campo in CAMPOS_CLAVE_ESCANEADO:
        resuelto = campo in aceptados or campo in negados
        if campo == "/requisitos/ingresos_max_iprem" and _POR_MIEMBROS in aceptados:
            resuelto = True
        if not resuelto and campo not in descartes:
            descartes[campo] = Descarte(campo, "pdf_escaneado")
