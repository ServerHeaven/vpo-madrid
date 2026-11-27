"""PDF reading. Every document is built in memory; the content is made up."""

import hashlib

import pdfplumber
import pymupdf
import pytest

from vpo.extraction.documents import pdf as modulo
from vpo.extraction.documents.pdf import DocumentoIlegible, leer_pdf
from vpo.extraction.preprocess import preparar

URL = "https://example.org/bases.pdf"
LARGA = "Bases ficticias de una convocatoria de alquiler que no existe en ninguna parte."


def crear_pdf(*paginas, **guardado) -> bytes:
    """Each page is a function that draws on it."""
    with pymupdf.open() as doc:
        for dibujar in paginas:
            dibujar(doc.new_page(width=595, height=842))
        return doc.tobytes(**guardado)


def lineas(*textos, x=72, y=100, salto=14, tam=11):
    def dibujar(page):
        for i, texto in enumerate(textos):
            page.insert_text((x, y + i * salto), texto, fontsize=tam)

    return dibujar


def rejilla(page, filas, *, x=72, y=200, ancho=120, alto=24):
    columnas = len(filas[0])
    for i in range(len(filas) + 1):
        page.draw_line((x, y + i * alto), (x + columnas * ancho, y + i * alto))
    for j in range(columnas + 1):
        page.draw_line((x + j * ancho, y), (x + j * ancho, y + len(filas) * alto))
    for i, fila in enumerate(filas):
        for j, celda in enumerate(fila):
            if celda:
                page.insert_text((x + j * ancho + 4, y + i * alto + 16), celda, fontsize=10)


def con_tabla(page):
    lineas(LARGA)(page)
    rejilla(page, [["Dormitorios", "Renta"], ["1", "450"], ["2", ""]])


def test_texto_bloques_y_hash():
    data = crear_pdf(lineas(LARGA), lineas("Segunda " + LARGA))
    doc = leer_pdf(data, URL)
    assert (doc.url, doc.tipo, doc.necesita_ocr) == (URL, "pdf", False)
    assert doc.sha256 == hashlib.sha256(data).hexdigest()
    assert [p.numero for p in doc.paginas] == [1, 2]
    assert doc.paginas[0].texto == LARGA
    bloque = doc.paginas[0].bloques[0]
    assert bloque.texto == LARGA
    assert bloque.bbox[0] == pytest.approx(72, abs=1) and bloque.bbox[3] > bloque.bbox[1]
    assert (doc.texto, doc.busqueda, doc.parrafos, doc.secciones) == ("", "", (), {})


def test_salida_determinista():
    data = crear_pdf(con_tabla)
    assert leer_pdf(data, URL) == leer_pdf(data, URL)


def test_orden_de_lectura_vertical_aunque_se_escriba_al_reves():
    def dibujar(page):
        page.insert_text((72, 400), "Abajo: " + LARGA)
        page.insert_text((72, 100), "Arriba: " + LARGA)

    texto = leer_pdf(crear_pdf(dibujar), URL).paginas[0].texto
    assert texto.index("Arriba") < texto.index("Abajo")


def test_dos_columnas_se_leen_una_tras_otra():
    def dibujar(page):
        page.insert_text((72, 60), "TITULO A TODO EL ANCHO DE LA PAGINA, ANTES DE LAS DOS COLUMNAS DE TEXTO")
        for i in range(12):
            page.insert_text((40, 100 + i * 30), f"izquierda {i} de la columna primera con texto", fontsize=10)
            page.insert_text((315, 100 + i * 30), f"derecha {i} de la columna segunda con texto", fontsize=10)

    texto = leer_pdf(crear_pdf(dibujar), URL).paginas[0].texto
    assert texto.startswith("TITULO")
    assert texto.index("izquierda 11") < texto.index("derecha 0 ")


def test_celdas_cortas_en_dos_lados_no_son_columnas():
    def dibujar(page):
        for i, (a, b) in enumerate([("uno", "450"), ("dos", "560")]):
            page.insert_text((72, 100 + i * 40), a)
            page.insert_text((400, 100 + i * 40), b)

    assert leer_pdf(crear_pdf(dibujar), URL).paginas[0].texto.split() == ["uno", "450", "dos", "560"]


def test_texto_girado_va_al_final():
    def dibujar(page):
        page.insert_text((30, 600), "Sello vertical del margen", rotate=90)
        lineas(LARGA)(page)

    bloques = leer_pdf(crear_pdf(dibujar), URL).paginas[0].bloques
    assert [b.texto for b in bloques] == [LARGA, "Sello vertical del margen"]


def test_tablas_con_celdas_vacias():
    pagina = leer_pdf(crear_pdf(con_tabla), URL).paginas[0]
    assert pagina.tablas == ((("Dormitorios", "Renta"), ("1", "450"), ("2", "")),)


def test_un_recuadro_con_un_solo_texto_no_es_tabla():
    def dibujar(page):
        lineas(LARGA)(page)
        rejilla(page, [["Aviso"]], ancho=300)

    assert leer_pdf(crear_pdf(dibujar), URL).paginas[0].tablas == ()


def test_fallo_de_pdfplumber_en_una_pagina_no_pierde_el_documento(monkeypatch):
    original = pdfplumber.page.Page.extract_tables

    def falla_en_la_primera(self, *args, **kwargs):
        if self.page_number == 1:
            raise RuntimeError("fallo simulado")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pdfplumber.page.Page, "extract_tables", falla_en_la_primera)
    doc = leer_pdf(crear_pdf(con_tabla, con_tabla), URL)
    assert LARGA in doc.paginas[0].texto
    assert doc.paginas[0].tablas == ()
    assert len(doc.paginas[1].tablas) == 1


def test_fallo_de_pdfplumber_al_abrir_conserva_el_texto(monkeypatch):
    def falla(*args, **kwargs):
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr(modulo.pdfplumber, "open", falla)
    doc = leer_pdf(crear_pdf(con_tabla), URL)
    assert LARGA in doc.paginas[0].texto and doc.paginas[0].tablas == ()


def test_pdf_escaneado(monkeypatch):
    def no_debe_llamarse(*args, **kwargs):
        raise AssertionError("no se buscan tablas en un PDF escaneado")

    monkeypatch.setattr(modulo, "_leer_tablas", no_debe_llamarse)
    doc = leer_pdf(crear_pdf(lambda page: page.draw_rect((50, 50, 500, 700)), lineas("pag 2")), URL)
    assert doc.necesita_ocr
    assert len(doc.paginas) == 2 and doc.paginas[0].tablas == ()


@pytest.mark.parametrize(("caracteres", "escaneado"), [(49, True), (50, False)])
def test_umbral_de_escaneado_por_media(caracteres, escaneado):
    data = crear_pdf(lineas("x" * (caracteres * 2), tam=6), lambda page: None)
    assert leer_pdf(data, URL).necesita_ocr is escaneado


@pytest.mark.parametrize(
    "data", [b"", b"<html>No es un PDF</html>", b"%PDF-1.7\nbasura sin objetos", b"PK\x03\x04" + b"0" * 100]
)
def test_ficheros_ilegibles(data):
    with pytest.raises(DocumentoIlegible):
        leer_pdf(data, URL)


def test_protegido_con_contrasena():
    data = crear_pdf(
        lineas(LARGA), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secreta", owner_pw="otra"
    )
    with pytest.raises(DocumentoIlegible, match="contraseña"):
        leer_pdf(data, URL)


def test_demasiadas_paginas(monkeypatch):
    monkeypatch.setattr(modulo, "MAX_PAGINAS", 2)
    with pytest.raises(DocumentoIlegible, match="páginas"):
        leer_pdf(crear_pdf(*[lineas(LARGA)] * 3), URL)


def test_demasiados_caracteres(monkeypatch):
    monkeypatch.setattr(modulo, "MAX_CARACTERES", 10)
    with pytest.raises(DocumentoIlegible, match="caracteres"):
        leer_pdf(crear_pdf(lineas(LARGA)), URL)


def test_documento_ilegible_es_value_error():
    assert issubclass(DocumentoIlegible, ValueError)


def test_de_extremo_a_extremo():
    def pagina(n, *cuerpo):
        def dibujar(page):
            page.insert_text((72, 40), "Convocatoria ficticia de alquiler protegido")
            lineas(*cuerpo)(page)
            page.insert_text((290, 810), f"Página {n} de 3")

        return dibujar

    data = crear_pdf(
        pagina(1, "BASE 3. REQUISITOS", "Los solicitantes deberán tener ingresos no superiores a 5,5 veces el"),
        pagina(2, "IPREM y estar empadronados en el municipio de forma ininterrumpida y estar al co-", "rriente."),
        pagina(3, "ANEXO I", "Cuadro de rentas ficticias de la promoción que no existe."),
    )
    doc = preparar(leer_pdf(data, URL))
    assert "Convocatoria ficticia" not in doc.texto and "Página" not in doc.texto
    assert "5,5 veces el IPREM y estar empadronados" in doc.texto
    assert "al corriente." in doc.texto
    pos = doc.busqueda.index("5,5 veces")
    assert (doc.pagina_en(pos), doc.parrafo_en(pos).seccion) == (1, "requisitos")
    assert doc.secciones["anexo"].pag_ini == 3
