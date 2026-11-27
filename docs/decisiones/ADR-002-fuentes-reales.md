# ADR-002: ajustes del diseño a las webs reales (Fase 2)

**Estado:** puntos 1 a 3 aceptados (2026-11-27); puntos de «Abierto» pendientes de decisión.

## 1. Plan Vive: un registro por municipio
`comunidad.madrid/plan-vive` no tiene fichas por promoción, sino un bloque por municipio (26 el 2026-11-27) con totales agregados.

**Decisión:** cada bloque es una «promoción» agregada. `viviendas_total` es la suma del municipio y las `tipologias` solo indican dormitorios. El detalle por promoción llegará, en su caso, con las operadoras (Fase 5).

**Consecuencias:**
- La identidad de la ficha es `https://www.comunidad.madrid/plan-vive#<municipio>`. El ancla no existe en la página (el enlace abre arriba), pero distingue los registros. Por eso `state.promo_ids` usa la URL de ficha tal cual, con fragmento, y `state.documentos` la URL canónica sin él (§3.4 hablaba de URL canónica para ambos).
- Los ids repiten el municipio (`comunidad-de-madrid-getafe-plan-vive-getafe`) por la regla de §3.1.
- Cuando se añadan las operadoras habrá que decidir cómo no duplicar viviendas entre el agregado y sus fichas.
- `enlaces.solicitud` solo se rellena si el municipio tiene un único enlace de inscripción.

## 2. EMVS Madrid: «en proyecto y obra» más el sorteo
**Decisión:** se incluyen las promociones de `/nuestras-promociones/en-proyecto-y-obra` (estado `proxima`) y la de `/Vivienda/SorteoPromocion`. El resto de finalizadas queda fuera.

**A 2026-11-27 no hay sorteo abierto:** la página indica que el plazo de Iberia Loreto 1 terminó el 11/06/2026, así que sale como `inscripcion_cerrada`. El botón «Inscríbete» solo existe dentro de un comentario HTML.

**Consecuencia:** si EMVS retira la página del sorteo o deja de enlazar una única ficha, la fuente entera pasa a `error` y conserva el último dato bueno hasta que se revise el adaptador. Es deliberado: no se puede distinguir un sorteo retirado de un cambio de HTML.

## 3. Empadronamiento del Plan Vive (ADR-001 §2)
**Decisión:** solución provisional. `empadronamiento = null` y la preferencia se describe en `requisitos.otros`, sin número de años porque las fuentes oficiales discrepan (ver [verificaciones](../verificaciones.md)). El schema no cambia.

## Detalles de implementación
- Con `httpx` basta en ambas fuentes: no se usa Playwright.
- `www.comunidad.madrid` declara `Crawl-delay: 10`; `intervalo_s` es 10 en esa fuente.
- La retirada a los 30 días se cuenta desde `meta.ultima_modificacion`, que en una promoción inactiva es el día en que desapareció. No ha hecho falta un campo nuevo.
- Una fuente `degradado` no actualiza `ultimo_exito`, para poder medir cuántos días lleva así.
- `documentos()` existe en los adaptadores, pero el orquestador no lo llama ni descarga PDFs hasta la Fase 3; `enlaces.bases` queda vacío.
- `campos_pendientes` queda vacío: la revisión es de la Fase 3.

## Abierto

### A. VPPA no significa lo que dice `programas.json`
EMVS usa «VPPA» como vivienda con protección pública para **arrendamiento** (Iberia Loreto 1, VPPA, admite de 18 a 50 años). La entrada `VPPA` de `programas.json` describe el arrendamiento **con opción de compra para jóvenes** (edad máxima 35). Si la calculadora aplicara ese valor por defecto, descartaría por edad a solicitantes de varias promociones de EMVS.

**Propuesta:** revisar el Decreto 74/2009 y separar ambos conceptos antes de la Fase 5. No se ha modificado `programas.json`.

### B. Modalidad supuesta en 8 promociones de EMVS
Barrio del Aeropuerto 1, Mahou Calderón, Ntra. Sra. de los Ángeles 3, Ofelia Nieto 3, Paseo de la Dirección 4 y 5, y Vallecas 71 y 72 no indican régimen de tenencia en su ficha. `modalidad` es obligatoria y no admite `null`, así que figuran como `alquiler` sin `procedencia`. Choca con «`null` antes que adivinar».

**Propuesta:** permitir `modalidad: null`. **Decidir antes de la Fase 4.**

### C. Para la Fase 3
- El hash de una página se registra aunque el análisis de su ficha haya fallado. Si se usa el hash para saltarse trabajo, habrá que excluir esas páginas.
- `bases[].detectado_en` deberá conservar el valor anterior para no generar cambios diarios.
- Los ids nuevos no se comprueban contra `promociones_manuales`; la fusión lo avisaría como `id_duplicado`.
