# /// script
# requires-python = ">=3.12"
# dependencies = ["openpyxl"]
# ///
"""Genera data/municipios.json a partir de la relación oficial del INE.

Herramienta manual (el scraper no la usa). Descarga antes
https://www.ine.es/daco/daco42/codmun/diccionario26.xlsx y ejecuta:

    uv run scraper/tools/gen_municipios.py diccionario26.xlsx 2026-01-01 data/municipios.json
"""

import json
import re
import sys
from pathlib import Path

import openpyxl


def nombre_legible(nombre_ine: str) -> str:
    """'Acebeda, La' -> 'La Acebeda'."""
    m = re.fullmatch(r"(.+), (El|La|Los|Las)", nombre_ine)
    return f"{m[2]} {m[1]}" if m else nombre_ine


def main(origen: str, fecha: str, destino: str) -> None:
    hoja = openpyxl.load_workbook(origen, read_only=True).active
    filas = list(hoja.iter_rows(values_only=True))
    cabecera = next(i for i, fila in enumerate(filas) if "CPRO" in fila)
    col = {nombre: i for i, nombre in enumerate(filas[cabecera]) if nombre}
    municipios = []
    for fila in filas[cabecera + 1 :]:
        if fila[col["CPRO"]] != "28":
            continue
        nombre_ine = fila[col["NOMBRE"]].strip()
        municipios.append(
            {
                "ine": f"28{fila[col['CMUN']]}",
                "nombre": nombre_legible(nombre_ine),
                "nombre_ine": nombre_ine,
            }
        )
    municipios.sort(key=lambda m: m["ine"])
    salida = {
        "$schema": "./schema/municipios.schema.json",
        "schema_version": 1,
        "fuente": "INE, relación de municipios y códigos (https://www.ine.es/daco/daco42/codmun/)",
        "fecha_referencia": fecha,
        "municipios": municipios,
    }
    texto = json.dumps(salida, ensure_ascii=False, indent=2) + "\n"
    Path(destino).write_text(texto, encoding="utf-8", newline="\n")
    print(f"{len(municipios)} municipios -> {destino}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
