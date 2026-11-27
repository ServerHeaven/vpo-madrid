# ADR-004: la web estática (Fase 4)

**Estado:** el punto 1 está decidido (2026-11-27); el resto describe cómo se ha concretado el diseño.

## 1. Astro 7 en lugar de Astro 5
§1 fijaba Astro 5. Al empezar la fase, la última versión de esa rama (5.18.2) arrastraba avisos de seguridad, uno crítico, corregidos solo en 7.x. Afectan sobre todo a SSR, servidor de desarrollo y optimización de imágenes, que este sitio no usa.

**Decidido (2026-11-27): Astro 7.** `npm audit` queda sin avisos. Consecuencias:
- Node 22.23.4 o superior.
- `compressHTML: true`: el valor por defecto de Astro 7 (`'jsx'`) pega palabras cuando un elemento en línea va tras un salto de línea.

## 2. Otras decisiones tomadas en esta fase
Registradas donde se plantearon:
- `modalidad` admite `null` ([ADR-002](ADR-002-fuentes-reales.md) B).
- La web no aplica los valores generales de `VPPA` salvo con opción de compra (ADR-002 A, **provisional**).
- `deploy.yml` fusiona y valida antes de construir ([ADR-001](ADR-001-huecos-del-diseno.md) §3).

## 3. Cómo se ha concretado el diseño
**Buscador**
- La isla recibe el índice como propiedades y se renderiza en el servidor: la lista completa se ve sin JavaScript y no hay una petición aparte. `data/index.json` se genera igualmente con la misma estructura.
- El índice solo lleva lo que usa el buscador. La Fase 5 añadirá lo que necesite la calculadora.
- Dormitorios, renta, garaje y trastero deben cumplirse en una misma tipología.
- Un dato desconocido no cumple un filtro. Se indica cuántas promociones se ocultan por falta de datos.
- Los filtros y el orden por renta sin ningún dato detrás no se ofrecen (salvo que una URL compartida ya los pida).
- Parámetros de URL: `mun`, `reg`, `prog`, `estado`, `renta_min`, `renta_max`, `dorm`, `garaje`, `trastero`, `abierta`, `orden`.

**Ficha**
- El origen «De la convocatoria» reúne lo leído de la web oficial y del PDF.
- No se muestran los fragmentos de texto extraídos (§7.4): se enlaza la fuente. De las correcciones manuales sí se muestra el motivo.
- Si no hay registro de la página de la promoción, «Última comprobación» usa la última lectura correcta de la fuente y lo dice. Las promociones manuales indican que no se comprueban solas.

**Datos en el build**
- `scripts/validar.mjs` valida todo `data/` contra los schemas; el build falla si algo no cumple.
- Las comprobaciones entre ficheros (ids repetidos, códigos INE, `no_exigidos`) siguen solo en `vpo validate`, que `deploy.yml` ejecuta.
- `src/lib/types.ts` se genera con `npm run gen:types`; no se edita a mano.

## 4. Criterios de «hecho» (§8) a 2026-11-27
- **Lighthouse:** medido en local sobre `astro preview` (móvil y escritorio): 100 en buscador, ficha, fuentes y metodología. Falta medirlo sobre la URL publicada.
- **Publicación:** pendiente. Hay que activar *Settings → Pages → Source: GitHub Actions* y subir los commits.
- **«Todas las fichas con PDF»: no se cumple.** Solo 1 de 44 promociones enlaza bases; las demás lo dicen en la ficha.
- Hoy no hay ninguna renta, garaje ni trastero conocidos, así que esos filtros no aparecen.
