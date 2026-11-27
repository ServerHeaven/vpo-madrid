# ADR-003: ajustes y límites de la extracción de PDF (Fase 3)

**Estado:** los ajustes están aplicados; los puntos de «Abierto» están pendientes de decisión.

## Cómo se ha concretado el diseño
- **Caché de candidatos** en `.cache/extraction/`, por hash del fichero y municipio. Permite no reextraer un PDF sin cambios (§3.4) y a la vez mostrar en el issue lo que se vio. Los PDF descargados quedan en `.cache/pdf/`. Todo es desechable.
- **Versión:** `extractor_version` es la versión del paquete (0.3.0). Un cambio de *minor* o superior reextrae; un *patch*, no.
- **`vpo reparse`** equivale a `vpo run --forzar-reparse`: vuelve a extraer todos los PDF. Las descargas siguen siendo condicionales.
- **Fusión con el HTML:** el HTML gana siempre. Un valor distinto en el PDF se descarta sin aviso.
- **Tablas de rentas:** las que tienen las mismas columnas y cuentan viviendas (una por promoción) forman una sola lista. Las demás quedan separadas y, si difieren, en conflicto.
- **Issues:** se listan los abiertos por etiqueta y se compara el marcador oculto en local, en vez de usar `--search`.
- **PyMuPDF fijado por debajo de la 2.0:** la 2.x añade `onnxruntime`, `numpy` y modelos de maquetación. PyMuPDF se distribuye bajo AGPL, y el código del proyecto es MIT.

## Lo que no se extrae
- `no_titular_vivienda` y `estado`: no están en las familias de reglas.
- Tipologías sin columna de renta (REG-RENTA-01 la exige).
- Fechas sin año, aunque el año se deduzca del documento.
- El heartbeat (issue `infra`) y `scrape.yml` son de la Fase 5.

## Calidad medida (2026-11-27)
Sobre 10 PDF: precisión 1,00 (50/50), cobertura 0,71.

**No es una medida independiente.** Las reglas se escribieron y corrigieron mirando estos documentos. Antes de la última ronda de correcciones la precisión fue 0,94, y un documento añadido después destapó un error (0,98). Con documentos nuevos cabe esperar menos de 1,00.

Además:
- `planvive_lote5_navalcarnero` y su versión de 2026 son casi idénticos: hay 9 documentos independientes, no 10.
- Ningún documento prueba el caso de PDF escaneado, `ingresos_por_miembros`, la fecha de sorteo, la entrega prevista ni `no_exigidos`. Esas reglas solo tienen tests con textos sintéticos.
- Solo EMVS enlaza bases hoy: con las webs reales hay un único PDF en uso (Iberia Loreto 1).

## Abierto

### A. Empadronamiento con dos vías
Las bases de Iberia Loreto 1 admiten «5 años ininterrumpidos **o** 8 dentro de los últimos 10». El HTML solo dice 5, y el schema no puede expresar la alternativa. Se publica 5, así que la calculadora podría descartar a quien cumple por la segunda vía. Decidir antes de la Fase 5.

### B. Tasa de esfuerzo con gastos incluidos
En Rivas el 30 % se refiere a renta, comunidad y suministros. Se guarda como `tasa_esfuerzo_max = 0.3`, que la calculadora aplicará solo a la renta (más permisivo). Relacionado con ADR-001 §4.

### C. Umbrales para un futuro LLM
§5.1 dice que un candidato LLM (confianza máxima 0,7) solo rellena huecos. Con los umbrales actuales (aceptar 0,8; conflicto 0,5) nunca rellena nada y, si discrepa de una regla, anula el campo. Hay que ajustarlo antes de implementar `LLMExtractor`.
