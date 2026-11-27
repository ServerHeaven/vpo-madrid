"""Income limits in IPREM (REG-IPREM-01..06) and maximum effort rate (REG-ESF-01..02).

Precision first: a figure needs an unambiguous minimum/maximum context, and figures belonging to a
priority, a quota, a guarantee or a special group of applicants are ignored.
"""

from __future__ import annotations

import re

from ..base import Document, ExtractionContext, FieldResult, Table, plegar
from ..patterns import NUMBER_WORDS, ingresos as p, to_number

_MIN = "/requisitos/ingresos_min_iprem"
_MAX = "/requisitos/ingresos_max_iprem"
_MIEMBROS = "/requisitos/ingresos_por_miembros"
_PAGAS = "/requisitos/iprem_pagas"
_EJERCICIO = "/requisitos/iprem_ejercicio"
_ESFUERZO = "/requisitos/tasa_esfuerzo_max"
_SECCION = "requisitos"
_PAGAS_VALOR = {"12": 12, "doce": 12, "14": 14, "catorce": 14}


class IngresosIpremExtractor:
    nombre = "ingresos_iprem"
    version = "1.0.0"
    campos_soportados = frozenset({_MIN, _MAX, _MIEMBROS, _PAGAS, _EJERCICIO, _ESFUERZO})

    def extract(self, doc: Document, ctx: ExtractionContext) -> list[FieldResult]:
        tablas = _tablas(doc)
        # Figures already given per household size are not repeated as flat limits.
        en_tabla = {
            campo: {row[key] for r in tablas for row in r.valor if row[key] is not None}
            for campo, key in ((_MIN, "min_iprem"), (_MAX, "max_iprem"))
        }
        resultados = list(tablas)
        for oracion in p.oraciones(doc):
            resultados += [r for r in _limites(doc, oracion) if r.valor not in en_tabla[r.campo]]
            resultados += _pagas(doc, oracion)
            resultados += _ejercicio(doc, oracion)
            resultados += _esfuerzo(doc, oracion)
        return resultados


# -- flat limits ------------------------------------------------------------------------------


def _valor(match: re.Match[str], grupo: str, media: str | None) -> float | None:
    """The figure of a match; None if the number and its repetition between brackets disagree."""
    values = []
    for name in (grupo, f"{grupo}_bis"):
        text = match.group(name)
        if text is None:
            continue
        if " coma " in text:
            entero, decimal = (NUMBER_WORDS[part] for part in text.split(" coma "))
            values.append(entero + decimal / 10)
        else:
            values.append(to_number(text))
    if not values or any(v is None or v != values[0] for v in values):
        return None
    value = values[0] + (0.5 if media and match.group(media) else 0)
    return float(value)


def _limites(doc: Document, oracion: p.Oracion) -> list[FieldResult]:
    texto = oracion.texto
    if not p.IPREM_RE.search(texto):
        return []
    if p.PRIORIDAD_RE.search(texto) or p.PRIORIDAD_RE.search(oracion.entradilla) or p.OTRO_ASUNTO_RE.search(texto):
        return []

    def resultado(campo: str, valor: float, regla: str, base: float, desde: int, hasta: int) -> FieldResult:
        return doc.resultado(
            campo, valor, base, oracion.inicio + desde, oracion.inicio + hasta, regla, seccion=_SECCION
        )

    found: list[FieldResult] = []
    for match in p.MULTIPLICAR_RE.finditer(texto):
        valor = _valor(match, "n", None)
        if valor is not None and not p.EXCLUSION_RE.search(texto[: match.start()]):
            found.append(resultado(_MAX, valor, "REG-IPREM-01", 0.85, match.start(), match.end()))
    rangos: list[tuple[int, int]] = []
    for match in p.RANGO_IPREM_RE.finditer(texto):
        if match.group("nexo") not in p.NEXOS_DE_RANGO[match.group("prep")]:
            continue
        rangos.append(match.span())
        antes = texto[: match.start()]
        despues = texto[match.end() :]
        if p.EXCLUSION_RE.search(antes) or p.CONDICION_RE.search(antes) or p.SUFIJO_CONDICION_RE.match(despues):
            continue
        minimo = _valor(match, "a", "media_a")
        maximo = _valor(match, "b", "media_b")
        if minimo is None or maximo is None or minimo >= maximo:
            continue
        found.append(resultado(_MIN, minimo, "REG-IPREM-03", 0.9, match.start(), match.end()))
        found.append(resultado(_MAX, maximo, "REG-IPREM-03", 0.9, match.start(), match.end()))

    cantidades = [
        m
        for m in p.CANTIDAD_IPREM_RE.finditer(texto)
        if _es_cantidad(m, texto) and not any(a <= m.start() < b for a, b in rangos)
    ]
    previo_fin = 0
    previo_tipo: str | None = None
    for index, match in enumerate(cantidades):
        # The context of a figure starts where the previous figure or range ended.
        desde = max([previo_fin] + [b for _, b in rangos if b <= match.start()])
        ventana = texto[desde : match.start()]
        siguiente = cantidades[index + 1].start() if index + 1 < len(cantidades) else len(texto)
        sufijo = texto[match.end() : siguiente]
        previo_fin = match.end()
        # "5,5 veces para familias numerosas" is a special limit; "... si se trata de VPPB" is not.
        if p.CONDICION_RE.search(ventana) or (p.SUFIJO_CONDICION_RE.match(sufijo) and p.CONDICION_RE.search(sufijo)):
            previo_tipo = None
            continue
        tipo = _tipo_limite(texto, desde, match, ventana, previo_tipo)
        previo_tipo = tipo
        valor = _valor(match, "n", "media")
        if tipo is None or valor is None:
            continue
        campo, regla = (_MAX, "REG-IPREM-01") if tipo == "max" else (_MIN, "REG-IPREM-02")
        found.append(resultado(campo, valor, regla, 0.85, desde, match.end()))
    return found


def _es_cantidad(match: re.Match[str], texto: str) -> bool:
    es_palabra = not match.group("n")[0].isdigit()
    if match.group("iprem"):
        return bool(match.group("veces")) or not es_palabra
    resto = texto[match.end() :]
    if match.group("veces"):
        return bool(p.SIGUE_SIN_NOMBRE_RE.match(resto))
    return not es_palabra and bool(p.SIGUE_OTRO_LIMITE_RE.match(resto))


def _tipo_limite(texto: str, desde: int, match: re.Match[str], ventana: str, previo: str | None) -> str | None:
    """'min', 'max' or None when the context does not say which limit the figure is."""
    if p.AMBOS_LIMITES_RE.search(ventana):
        return None
    excluye_antes = bool(p.EXCLUSION_RE.search(texto[: match.start()]))
    sufijo = p.SUFIJO_RE.match(texto[match.end() :])
    por_sufijo = {"maximo": "max", "minimo": "min"}[sufijo.group("tipo")] if sufijo else None

    comparadores = list(p.COMPARADOR_RE.finditer(ventana))
    por_prefijo = None
    if comparadores:
        ultimo = comparadores[-1]
        clase = ultimo.lastgroup
        palabra = " ".join(ultimo.group().split())
        hueco = len(ventana) - ultimo.end()
        if hueco > p.MAX_HUECO_PREPOSICION.get(palabra, p.MAX_HUECO[clase]):
            return None
        if clase in ("max", "min"):
            por_prefijo = clase
        else:
            antes = texto[: desde + ultimo.start()]
            negado = bool(p.NEGADO_RE.search(antes))
            if not negado:
                # A distant "no" may negate the comparator; a bare verb does not say which limit it is.
                if p.NEGACION_CERCANA_RE.search(antes[-60:].rsplit(",", 1)[-1]) or clase == "verbo":
                    return None
                if p.EXCLUSION_RE.search(texto):
                    return None
            es_techo = clase in ("sup", "verbo")
            por_prefijo = "max" if es_techo == negado else "min"
    elif por_sufijo is None and previo and p.HEREDA_RE.match(ventana):
        por_prefijo = previo

    if excluye_antes or (por_prefijo and por_sufijo and por_prefijo != por_sufijo):
        return None
    return por_prefijo or por_sufijo


# -- payments and year ------------------------------------------------------------------------


def _pagas(doc: Document, oracion: p.Oracion) -> list[FieldResult]:
    found = []
    for match in p.PAGAS_RE.finditer(oracion.texto):
        antes = oracion.texto[max(match.start() - 80, 0) : match.start()]
        despues = oracion.texto[match.end() : match.end() + 40]
        nombres = list(p.IPREM_RE.finditer(antes))
        if nombres:
            hueco = antes[nombres[-1].end() :]
        else:
            nombre = p.IPREM_RE.search(despues)
            if nombre is None:
                continue
            hueco = despues[: nombre.start()]
        if p.PAGAS_AJENAS_RE.search(hueco) or p.PAGAS_AJENAS_RE.search(antes[-20:]):
            continue
        inicio = oracion.inicio + match.start()
        found.append(
            doc.resultado(
                _PAGAS,
                _PAGAS_VALOR[match.group("pagas")],
                0.9,
                inicio,
                oracion.inicio + match.end(),
                "REG-IPREM-05",
                seccion=_SECCION,
            )
        )
    return found


def _ejercicio(doc: Document, oracion: p.Oracion) -> list[FieldResult]:
    texto = oracion.texto
    if not p.EJERCICIO_CONTEXTO_RE.search(texto) or p.EJERCICIO_AJENO_RE.search(texto):
        return []
    if p.PRIORIDAD_RE.search(texto):
        return []
    return [
        doc.resultado(
            _EJERCICIO,
            int(match.group("y")),
            0.7,
            oracion.inicio + match.start(),
            oracion.inicio + match.end(),
            "REG-IPREM-06",
            seccion=_SECCION,
        )
        for match in p.EJERCICIO_RE.finditer(texto)
    ]


# -- effort rate ------------------------------------------------------------------------------


def _esfuerzo(doc: Document, oracion: p.Oracion) -> list[FieldResult]:
    texto = oracion.texto
    if p.ESFUERZO_AJENO_RE.search(texto) or p.PRIORIDAD_RE.search(texto) or p.PRIORIDAD_RE.search(oracion.entradilla):
        return []
    matches: list[tuple[re.Match[str], str, float]] = []
    for match in p.ESFUERZO_RENTA_RE.finditer(texto):
        if p.SUJETO_RENTA_RE.search(texto[max(match.start() - 150, 0) : match.start()]):
            matches.append((match, "REG-ESF-01", 0.85))
    matches += [(m, "REG-ESF-01", 0.85) for m in p.ESFUERZO_DESTINO_RE.finditer(texto)]
    if not matches:
        matches = [
            (m, "REG-ESF-02", 0.8)
            for m in p.ESFUERZO_TASA_RE.finditer(texto)
            if not re.search(r"minim|\bentre\b", m.group("hueco")) and "tasa de esfuerzo minima" not in texto
        ]
    return [
        doc.resultado(
            _ESFUERZO,
            int(match.group("p")) / 100,
            base,
            oracion.inicio + match.start(),
            oracion.inicio + match.end(),
            regla,
            seccion=_SECCION,
        )
        for match, regla, base in matches
    ]


# -- stepped table ----------------------------------------------------------------------------


def _tablas(doc: Document) -> list[FieldResult]:
    found = []
    for pagina in doc.paginas:
        for tabla in pagina.tablas:
            filas = _tabla_por_miembros(tabla)
            if filas:
                evidencia = " | ".join(" ".join(cell for cell in row if cell) for row in tabla)
                found.append(doc.resultado_tabla(_MIEMBROS, filas, 0.9, pagina.numero, evidencia, "REG-IPREM-04"))
    return found


def _celda(cell: str | None) -> str:
    return " ".join(plegar(cell or "").split())


def _miembros(cell: str) -> tuple[int, int | None] | None:
    """'3 o mas' -> (3, None). Anything not understood -> None."""
    texto = " ".join(p.MIEMBROS_RELLENO_RE.sub(" ", cell).split())
    for pattern, forma in p.MIEMBROS_FORMAS:
        match = pattern.fullmatch(texto)
        if not match:
            continue
        numeros = [NUMBER_WORDS.get(g) or int(g) for g in match.groups() if g is not None]
        if forma == "uno":
            rango = (numeros[0], numeros[0])
        elif forma == "desde":
            rango = (numeros[0], None)
        elif forma == "mas_de":
            rango = (numeros[0] + 1, None)
        elif forma == "hasta":
            rango = (1, numeros[0])
        else:
            rango = (numeros[0], numeros[1]) if numeros[0] < numeros[1] else None
        if rango is None or not 1 <= rango[0] <= 15:
            return None
        return rango
    return None


def _multiplo(texto: str) -> float | None:
    number = to_number(texto) if texto[:1].isdigit() else None
    return number if number is not None and 0 < number <= 15 else None


def _valores_columna(celdas: list[str], tipo: str | None) -> list[tuple[float | None, float | None]] | None:
    """(min, max) per row of one column, or None if any cell is not an IPREM multiple."""
    valores = []
    for cell in celdas:
        texto = " ".join(p.CELDA_RELLENO_RE.sub(" ", cell).split()).strip(" .")
        if texto in p.CELDA_VACIA or texto.startswith("sin "):
            valores.append((None, None))
            continue
        rango = p.CELDA_RANGO_RE.fullmatch(texto)
        if rango and tipo in (None, "rango"):
            bajo, alto = _multiplo(rango.group(1)), _multiplo(rango.group(2))
            if bajo is None or alto is None or bajo >= alto:
                return None
            valores.append((bajo, alto))
            continue
        hasta = p.CELDA_HASTA_RE.match(texto)
        number = _multiplo(texto[hasta.end() :] if hasta else texto)
        if number is None or tipo == "rango" or (tipo is None and not hasta) or (tipo == "min" and hasta):
            return None
        valores.append((number, None) if tipo == "min" else (None, number))
    return valores


def _cabeceras(filas: list[list[str]], ancho: int) -> list[str]:
    """Header text of each column; a spanning cell of an upper row covers the empty ones to its right."""
    columnas = [""] * ancho
    for index, fila in enumerate(filas):
        arrastre = ""
        for col in range(ancho):
            texto = fila[col]
            if texto:
                arrastre = texto
            elif index < len(filas) - 1 and col > 0:
                texto = arrastre
            columnas[col] = f"{columnas[col]} {texto}".strip()
    return columnas


def _tabla_por_miembros(tabla: Table) -> list[dict] | None:
    filas = [[_celda(cell) for cell in row] for row in tabla]
    filas = [row for row in filas if any(row)]
    if len(filas) < 2:
        return None
    ancho = max(len(row) for row in filas)
    filas = [row + [""] * (ancho - len(row)) for row in filas]
    inicio = next((i for i, row in enumerate(filas) if any(_miembros(cell) for cell in row)), None)
    if not inicio:  # no data rows, or no header at all
        return None
    cabecera = " ".join(cell for row in filas[:inicio] for cell in row if cell)
    if "miembro" not in cabecera or not p.IPREM_RE.search(cabecera) or p.CABECERA_DESCARTADA_RE.search(cabecera):
        return None
    columnas = _cabeceras(filas[:inicio], ancho)
    datos = filas[inicio:]

    col_miembros = next(
        (
            col
            for col in range(ancho)
            if p.CABECERA_MIEMBROS_RE.search(columnas[col]) and all(_miembros(row[col]) for row in datos)
        ),
        None,
    )
    if col_miembros is None:
        return None

    minimos: list[list[float | None]] = []
    maximos: list[list[float | None]] = []
    for col in range(ancho):
        titulo = columnas[col]
        celdas = [row[col] for row in datos]
        if col == col_miembros or not any(celdas) or p.CABECERA_AJENA_RE.search(titulo):
            continue
        if any("€" in cell or "euro" in cell for cell in celdas):
            continue
        es_min, es_max = "minim" in titulo, "maxim" in titulo
        if es_min and es_max:
            tipo = "rango"
        elif es_min or es_max:
            tipo = "min" if es_min else "max"
        elif not (p.IPREM_RE.search(titulo) or "veces" in titulo):
            continue
        elif ("minim" in cabecera) != ("maxim" in cabecera):
            tipo = "min" if "minim" in cabecera else "max"
        else:
            tipo = None  # only cells that say it themselves ("hasta 5,5", "de 2 a 5,5")
        valores = _valores_columna(celdas, tipo)
        if valores is None:
            return None
        if any(low is not None for low, _ in valores):
            minimos.append([low for low, _ in valores])
        if any(high is not None for _, high in valores):
            maximos.append([high for _, high in valores])
    if len(minimos) > 1 or len(maximos) > 1 or not (minimos or maximos):
        return None

    resultado = []
    for index, row in enumerate(datos):
        desde, hasta = _miembros(row[col_miembros])
        bajo = minimos[0][index] if minimos else None
        alto = maximos[0][index] if maximos else None
        if (bajo is None and alto is None) or (bajo is not None and alto is not None and bajo >= alto):
            return None
        resultado.append({"miembros_desde": desde, "miembros_hasta": hasta, "min_iprem": bajo, "max_iprem": alto})
    resultado.sort(key=lambda r: r["miembros_desde"])
    for previo, actual in zip(resultado, resultado[1:]):
        if previo["miembros_hasta"] is None or actual["miembros_desde"] <= previo["miembros_hasta"]:
            return None
    return resultado
