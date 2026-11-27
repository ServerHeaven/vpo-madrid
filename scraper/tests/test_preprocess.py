"""One group of tests per transformation of ARCHITECTURE.md §5.2. All texts are made up."""

import pytest

from vpo.extraction.base import SEPARADOR_PARRAFOS, Block, Document, Page, plegar
from vpo.extraction.preprocess import (
    asignar_secciones,
    clasificar_encabezado,
    colapsar_espacios,
    dividir_bloque,
    entradas_de_indice,
    es_normativo,
    limpiar_tabla,
    lineas_repetidas,
    normalizar_unicode,
    preparar,
    reconstruir_parrafos,
    unir_lineas,
)


def documento(*paginas: Page) -> Document:
    return Document(url="https://example.org/bases.pdf", tipo="pdf", sha256="0" * 64, paginas=paginas)


def pagina(numero: int, *bloques: str, salto: float = 4.0) -> Page:
    """Blocks stacked downwards, 12 points per line and ``salto`` between blocks."""
    y = 80.0
    resultado = []
    for texto in bloques:
        alto = 12.0 * (texto.count("\n") + 1)
        resultado.append(Block((72.0, y, 520.0, y + alto), texto))
        y += alto + salto
    return Page(numero, "\n\n".join(bloques), tuple(resultado))


def parrafos(*paginas: Page) -> list[str]:
    return [texto for _, texto in reconstruir_parrafos(paginas)]


# -- characters and spaces ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "salida"),
    [
        ("ﬁanza y oﬃcial", "fianza y official"),
        ("“renta” ‘máxima’ «útil»", "\"renta\" 'máxima' \"útil\""),
        ("60 m² útiles aprox", "60 m2 útiles aprox"),
        ("empa­dronado​", "empadronado"),
        ("vivien­", "vivien-"),
        (" Ser mayor de edad", "• Ser mayor de edad"),
    ],
)
def test_normalizar_unicode(entrada, salida):
    assert normalizar_unicode(entrada) == salida


@pytest.mark.parametrize("texto", ["5,5 veces el IPREM", "Año 2027: 450 €", "Fuencarral-El Pardo"])
def test_normalizar_unicode_no_cambia_texto_normal(texto):
    assert normalizar_unicode(texto) == texto


def test_colapsar_espacios():
    assert colapsar_espacios("  5,5   veces\t el  ") == "5,5 veces el"
    assert colapsar_espacios("ya limpio") == "ya limpio"


# -- de-hyphenation -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lineas", "texto"),
    [
        (["vivien-", "da protegida"], "vivienda protegida"),
        (["Fuencarral-", "El Pardo"], "Fuencarral-El Pardo"),
        (["curso 2026-", "2027"], "curso 2026-2027"),
        (["el municipio -", "o la comarca"], "el municipio - o la comarca"),
        (["ingresos no", "superiores"], "ingresos no superiores"),
        (["Fuencarral-El Pardo"], "Fuencarral-El Pardo"),
    ],
)
def test_unir_lineas(lineas, texto):
    assert unir_lineas(lineas) == texto


# -- headers and footers --------------------------------------------------------------------


def _paginas_con_cabecera(total: int) -> list[list[str]]:
    return [
        ["Bases de la convocatoria ficticia", f"Contenido propio {'abcdefgh'[n]}", f"Pág. {n + 11}", f"{n + 1}"]
        for n in range(total)
    ]


def test_cabeceras_y_numeros_de_pagina_repetidos():
    assert lineas_repetidas(_paginas_con_cabecera(4)) == [{0, 2, 3}] * 4


@pytest.mark.parametrize("total", [1, 2])
def test_documentos_cortos_no_pierden_nada(total):
    assert lineas_repetidas(_paginas_con_cabecera(total)) == [set()] * total


def test_solo_si_se_repite_en_mas_del_60_por_ciento():
    paginas = [[f"texto {c}"] for c in "abcde"]
    for lineas in paginas[:3]:  # exactly 60 %
        lineas.insert(0, "Cabecera parcial")
    assert lineas_repetidas(paginas) == [set()] * 5
    paginas[3].insert(0, "Cabecera parcial")
    assert [bool(s) for s in lineas_repetidas(paginas)] == [True] * 4 + [False]


def test_cifras_distintas_no_se_confunden_con_numeros_de_pagina():
    paginas = [[f"Renta mensual: {renta} euros"] for renta in (450, 610, 700, 820)]
    assert lineas_repetidas(paginas) == [set()] * 4


def test_lineas_repetidas_en_el_cuerpo_no_se_tocan():
    relleno = "abcdefghijklmnopqrstuvwxyz"
    paginas = [
        [f"antes {relleno[i]}{n * 7}z" for i in range(6)]
        + ["Se mantiene esta frase"]
        + [f"fin {relleno[i]}{n * 7}z" for i in range(6)]
        for n in range(4)
    ]
    assert lineas_repetidas(paginas) == [set()] * 4


def test_preparar_quita_cabeceras():
    doc = preparar(documento(*[pagina(n, "EMV ficticia", f"Cuerpo de la hoja {'xyz'[n - 1]}.", str(n)) for n in (1, 2, 3)]))
    assert doc.texto == SEPARADOR_PARRAFOS.join(f"Cuerpo de la hoja {c}." for c in "xyz")


# -- paragraphs -----------------------------------------------------------------------------

LINEA = "Los ingresos de la unidad de convivencia deberan ser no superiores a 5,5 veces el"


def test_frase_partida_en_varios_bloques():
    assert parrafos(pagina(1, LINEA, "IPREM del ejercicio.")) == [f"{LINEA} IPREM del ejercicio."]


def test_frase_partida_con_interlineado_doble():
    texto = ["ingresos no superiores", "a 5,5 veces", "el IPREM."]
    assert parrafos(pagina(1, *texto, salto=14)) == [" ".join(texto)]


def test_frase_partida_entre_paginas_empieza_en_la_primera():
    assert reconstruir_parrafos([pagina(1, LINEA), pagina(2, "IPREM vigente.")]) == [(1, f"{LINEA} IPREM vigente.")]


def test_palabra_cortada_entre_bloques():
    assert parrafos(pagina(1, "Se adjudicara una vivien-", "da por solicitud.")) == [
        "Se adjudicara una vivienda por solicitud."
    ]


def test_puntos_y_aparte_se_conservan():
    assert parrafos(pagina(1, "Primera frase completa.", "Segunda frase completa.")) == [
        "Primera frase completa.",
        "Segunda frase completa.",
    ]


def test_un_hueco_grande_separa_parrafos():
    assert len(parrafos(pagina(1, LINEA, "IPREM del ejercicio.", salto=60))) == 2


def test_etiquetas_cortas_sin_puntuacion_no_se_unen():
    assert parrafos(pagina(1, "Promocion ficticia", "Sesenta viviendas")) == ["Promocion ficticia", "Sesenta viviendas"]


@pytest.mark.parametrize("marca", ["•", "-", "a)", "1.", "2º)"])
def test_elementos_de_lista_separados(marca):
    bloque = f"Los requisitos son:\n{marca} Ser mayor de edad\n{marca} Tener ingresos"
    assert len(parrafos(pagina(1, bloque))) == 3
    assert len(parrafos(pagina(1, *bloque.split("\n")))) == 3


def test_vineta_en_su_propio_bloque():
    assert parrafos(pagina(1, "•", "Ser mayor de edad.")) == ["• Ser mayor de edad."]


def test_celdas_de_una_misma_fila_forman_una_linea():
    bloques = tuple(
        Block((x, 80.0, x + 60, 92.0), texto) for x, texto in ((72, "Plazo:"), (200, "del 1 al 15"), (300, "de marzo"))
    )
    assert parrafos(Page(1, "", bloques)) == ["Plazo: del 1 al 15 de marzo"]


def test_dividir_bloque_no_corta_frases_envueltas():
    lineas = ["una antiguedad minima de", "3. Y ademas ingresos no superiores a 5,5 veces el", "IPREM"]
    assert dividir_bloque(lineas, 50) == [lineas]


def test_dividir_bloque_no_corta_en_abreviaturas_ni_miles():
    lineas = ["segun el art.", "5 la renta sera de", "1.500 euros"]
    assert dividir_bloque(lineas, 40) == [lineas]


def test_dividir_bloque_corta_tras_una_linea_corta_final():
    assert dividir_bloque(["Fin del apartado.", "Otro apartado distinto empieza"], 60) == [
        ["Fin del apartado."],
        ["Otro apartado distinto empieza"],
    ]


def test_anexo_mencionado_al_final_de_una_linea_no_es_titulo():
    lineas = ["La relacion de viviendas disponibles figura en el documento", "Anexo I de este escrito."]
    assert dividir_bloque(lineas, 60) == [lineas]


def test_titulos_en_su_propio_parrafo():
    bloque = "REQUISITOS DE LAS PERSONAS\nSOLICITANTES\nPodran inscribirse quienes cumplan lo siguiente"
    assert parrafos(pagina(1, bloque)) == [
        "REQUISITOS DE LAS PERSONAS SOLICITANTES",
        "Podran inscribirse quienes cumplan lo siguiente",
    ]


def test_sin_bloques_las_lineas_en_blanco_separan():
    doc = preparar(documento(Page(1, "ingresos no\nsuperiores\n\nrenta mensual")))
    assert [doc.texto[p.inicio : p.fin] for p in doc.parrafos] == ["ingresos no superiores", "renta mensual"]


# -- sections -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("titulo", "seccion"),
    [
        ("REQUISITOS", "requisitos"),
        ("BASE 3.ª REQUISITOS DE LOS SOLICITANTES", "requisitos"),
        ("TERCERA.- Requisitos de acceso", "requisitos"),
        ("4. Requisitos", "requisitos"),
        ("RÉGIMEN ECONÓMICO", "rentas"),
        ("RENTA Y FIANZA", "rentas"),
        ("Base 7. Precio del alquiler", "rentas"),
        ("PLAZO DE PRESENTACIÓN DE SOLICITUDES", "plazos"),
        ("5. Plazo de presentación", "plazos"),
        ("ANEXO I", "anexo"),
        ("Anexo II. Cuadro de rentas", "anexo"),
        ("BASE 2. Requisitos. Podrán optar las personas que acrediten ingresos suficientes.", "requisitos"),
        ("ARTÍCULO 5. REQUISITOS DE LAS PERSONAS SOLICITANTES", "requisitos"),
        ("Artículo 7.- Plazo de presentación", "plazos"),
        ("2. Requisitos para acceder a una vivienda de alquiler asequible del programa ficticio local", "requisitos"),
        ("III.-Requisitos de acceso", "requisitos"),
    ],
)
def test_encabezados_reconocidos(titulo, seccion):
    assert clasificar_encabezado(titulo)[1] == seccion


@pytest.mark.parametrize(
    "texto",
    [
        "Cumplir los requisitos de la convocatoria.",
        "1. Ser mayor de edad",
        "La renta mensual sera de 450 euros.",
        "Renta: 450",
        "VPPB",
        "3. REQUISITOS ............ 5",
        "NO SE ADMITIRAN SOLICITUDES FUERA DEL PLAZO SEÑALADO.",
    ],
)
def test_no_son_encabezados_de_seccion(texto):
    resultado = clasificar_encabezado(texto)
    assert resultado is None or resultado == (True, None) or resultado[1] is None


def test_asignar_secciones():
    textos = [
        "Introducción.",
        "BASE 1. REQUISITOS",
        "1. Ser mayor de edad",
        "BASE 2. SORTEO",
        "Se celebrará.",
        "ANEXO I",
        "CUADRO DE VIVIENDAS",
        "Dos dormitorios",
        "RENTAS",
        "450 euros",
    ]
    assert asignar_secciones(textos) == [
        "otros", "requisitos", "requisitos", "otros", "otros", "anexo", "anexo", "anexo", "rentas", "rentas",
    ]  # fmt: skip


def test_el_indice_no_abre_secciones():
    assert asignar_secciones(["REQUISITOS ........ 3", "Texto cualquiera."]) == ["otros", "otros"]


def test_indice_sin_puntos():
    indice = ["I-Objeto.", "II- Requisitos de acceso.", "III- Plazo de presentación.", "Anexo I. Listado"]
    cuerpo = ["I.-Objeto", "Texto.", "II.-Requisitos de acceso", "Ser mayor de edad.", "III.-Plazo de presentación"]
    textos = [*indice, *cuerpo, "ANEXO I. LISTADO"]
    assert entradas_de_indice(textos) == {0, 1, 2, 3}
    assert asignar_secciones(textos) == ["otros"] * 6 + ["requisitos", "requisitos", "plazos", "anexo"]


def test_titulos_repetidos_sueltos_no_son_indice():
    assert entradas_de_indice(["Requisitos", "Uno.", "Dos.", "Tres.", "Requisitos"]) == set()


def test_el_apartado_siguiente_cierra_la_seccion():
    textos = ["1. Requisitos de acceso", "1.1. Ser mayor de edad.", "2. Cupos", "Texto.", "III.-Plazo", "IV.-Listado"]
    assert asignar_secciones(textos) == ["requisitos", "requisitos", "otros", "otros", "plazos", "otros"]


def test_un_ordinal_no_es_un_apartado():
    textos = ["1. Requisitos de acceso", "2.º En los casos de divorcio", "Texto."]
    assert asignar_secciones([normalizar_unicode(t) for t in textos]) == ["requisitos"] * 3


def test_un_elemento_de_lista_no_cierra_la_seccion():
    textos = ["BASE 2. REQUISITOS", "1. Ser mayor de edad", "2. Tener ingresos", "3. Requisitos", "4. Estar al día."]
    assert asignar_secciones(textos) == ["requisitos"] * 5


# -- normative citations --------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "De conformidad con el Decreto 74/2009, las viviendas de precio limitado admiten 7,5 veces el IPREM.",
        "El artículo 5 del Reglamento fija ingresos de hasta 7,5 veces el IPREM.",
        "3. Según lo dispuesto en la Ley 9/2001, el suelo se destinará a vivienda.",
        "Artículo 12 del Decreto 74/2009: el precio máximo será revisable.",
        "El régimen aplicable resulta del Decreto 74/2009, la Orden 1/2010 y la Ley 6/1997.",
        "La disposición adicional segunda de la Ley 9/2001 regula el suelo.",
    ],
)
def test_parrafos_normativos(texto):
    assert es_normativo(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "Los ingresos no podrán superar 5,5 veces el IPREM, de conformidad con el Decreto 74/2009.",
        "Las viviendas, calificadas conforme al Decreto 74/2009, exigen estar empadronado 3 años.",
        "De conformidad con el Decreto 74/2009, los solicitantes deberán ser mayores de edad.",
        "De acuerdo con la Ley 9/2001, en la presente convocatoria la renta es de 450 euros.",
        "Los ingresos se computarán en orden a su cuantía.",
        "DISPOSICIÓN ADICIONAL PRIMERA",
        "Artículo 5. Requisitos de acceso",
        "Ser mayor de edad.",
    ],
)
def test_parrafos_no_normativos(texto):
    assert not es_normativo(texto)


# -- tables and assembly --------------------------------------------------------------------


def test_limpiar_tabla():
    assert limpiar_tabla((("Dormi-\ntorios", "Renta\n  mensual"), ("1", ""))) == (
        ("Dormitorios", "Renta mensual"),
        ("1", ""),
    )


def test_preparar_offsets_busqueda_y_secciones():
    tabla = (("Renta\nmensual", "450 m²"),)
    original = documento(
        pagina(1, "RÉGIMEN ECONÓMICO", "La renta máxima será de 450 euros."),
        Page(2, "x", (Block((72, 80, 520, 92), "Según el Decreto 1/2000, otra cosa."),), (tabla,)),
    )
    doc = preparar(original)

    assert len(doc.busqueda) == len(doc.texto) and doc.busqueda == plegar(doc.texto)
    assert doc.texto == SEPARADOR_PARRAFOS.join(doc.texto[p.inicio : p.fin] for p in doc.parrafos)
    pos = doc.busqueda.index("maxima")
    assert doc.texto[pos : pos + 6] == "máxima"
    assert [(p.pagina, p.seccion, p.normativo) for p in doc.parrafos] == [
        (1, "rentas", False),
        (1, "rentas", False),
        (2, "rentas", True),
    ]
    assert (doc.secciones["rentas"].pag_ini, doc.secciones["rentas"].pag_fin) == (1, 2)
    assert doc.secciones["rentas"].texto == doc.texto
    assert doc.paginas[1].tablas == ((("Renta mensual", "450 m2"),),)
    assert (doc.url, doc.sha256, doc.necesita_ocr) == (original.url, original.sha256, original.necesita_ocr)
    assert original.texto == "" and original.paginas[1].tablas == (tabla,)


def test_preparar_documento_vacio():
    doc = preparar(documento(Page(1, "")))
    assert (doc.texto, doc.busqueda, doc.parrafos, doc.secciones) == ("", "", (), {})
