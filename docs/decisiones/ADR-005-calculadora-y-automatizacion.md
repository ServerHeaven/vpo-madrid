# ADR-005: calculadora y automatización (Fase 5)

**Estado:** el punto 1 describe cómo se ha concretado el diseño; el punto 2 está **pendiente de decisión**.

## 1. Cómo se ha concretado el diseño

**Calculadora**
- Los datos van a la isla como propiedades, resueltos en el build (§6.2) con las mismas funciones que las fichas. La página no hace ninguna petición tras cargar, ni siquiera de `data/index.json`, que sigue llevando solo lo del buscador (como en [ADR-004](ADR-004-web.md)).
- Un requisito en `null` es siempre DESCONOCIDO, también la titularidad: la nota de §6.3 (ADR-001 §1) prevalece sobre la fila R6.
- Ingresos: coeficiente por número de miembros y 14 pagas, ya publicados en `programas.json` ([verificaciones](../verificaciones.md)). Sin coeficiente conocido se comparan sin ponderar y se avisa.
- R8 no se evalúa: el schema no tiene datos de adecuación.
- Con tabla por miembros, un `ingresos_min_iprem` listado en `no_exigidos` no llega a la calculadora.
- R3 compara la renta más baja de cada horquilla.
- El formulario no puede enviarse de forma nativa (`method="dialog"`, sin atributos `name`, desactivado hasta la hidratación).

**Datos del Plan Vive**
- La entrada `PLAN_VIVE` pasa a `verificado: true` con el Decreto 84/2020 modificado por el Decreto 31/2026: mínimo 1,5 IPREM, coeficientes propios, 14 pagas y 35 %.
- Se retira la inscripción en el Registro de Demandantes, que no consta en ninguna fuente leída.

**Automatización**
- La programación diaria de `scrape.yml` está **comentada** hasta que una ejecución manual termine bien (§8).
- Un push con `GITHUB_TOKEN` no dispara `ci.yml` (§4.0), así que la guardia de propiedad de §4.3 **también** se ejecuta dentro de `scrape.yml` antes del commit. Sigue el criterio de §2: de `data/`, el bot solo escribe los tres tipos de fichero generados.
- El heartbeat es `vpo review heartbeat`; `vpo review health` cierra su issue tras una lectura reciente. Una ejecución manual de una sola fuente también cuenta como lectura.
- Sin caché de Playwright: ninguna fuente lo usa.
- Si `pull --rebase` trae cambios, se vuelven a fusionar y validar antes de subir; un conflicto deja el workflow en rojo.

## 2. Pendiente de decisión
1. **Base de la tasa de esfuerzo** (ADR-001 §4). La norma del Plan Vive confirma ingresos **netos**; §6.3 divide entre la cifra introducida (base imponible). Hoy no hay ninguna renta publicada, así que no cambia ningún resultado. Cuando las haya, un «cumple» puede ser optimista. Opciones: pedir los ingresos netos como dato opcional, o dejar R3 en DESCONOCIDO cuando la tasa venga de una norma sobre netos.
2. **14 pagas por defecto.** Ahora está respaldado por las fuentes de la Comunidad, pero en promociones sin entrada aplicable en `programas.json` sigue siendo una suposición que puede producir un «no elegible» por ingresos mínimos. Se avisa en cada caso.
3. **Coeficientes en VPPA de alquiler sin opción de compra.** [ADR-002](ADR-002-fuentes-reales.md) A impide aplicarles la entrada `VPPA`, de modo que tampoco reciben coeficiente y el máximo de ingresos les resulta más estricto.
4. **Año de ingresos por defecto.** §6.1 dice «año actual − 1»; de enero a junio suele corresponder año − 2. Se explica en la ayuda y en la metodología.

## 3. Alcance y criterios de «hecho» (§8)
- **Adaptadores nuevos:** §8 pide uno por PR, así que van en ramas aparte, no en `main`.
- **OCR:** opcional, no hecho.
- **No comprobado:** `actionlint` no se ha ejecutado y `scrape.yml` no se ha lanzado nunca en GitHub. Se ha comprobado la estructura YAML, la sintaxis de los scripts y, en un repositorio local desechable, el paso de commit.
- **Siete días de cron:** pendiente, requiere activarlo.
