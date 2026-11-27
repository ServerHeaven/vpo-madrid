# ADR-001: huecos del diseño detectados en la Fase 1

**Estado:** propuesto, pendiente de decisión. La Fase 1 implementa el diseño tal como está.

## 1. `null` significa a la vez "desconocido" y "no se exige"
§3.1 define `null` como "no lo sabemos". §6.3 (R2, R4, R5) trata `empadronamiento`, `edad` o ingresos mínimos en `null` como "no se exige", es decir, cumplido.

**Consecuencias:** si el extractor no encuentra el empadronamiento, la calculadora puede decir "elegible" a quien no lo es. Además, `empadronamiento` es campo clave: una convocatoria que de verdad no lo exige tendría el issue de revisión abierto para siempre (solo se cerraría con un override a `null`, que la calculadora no distinguiría).

**Propuesta:** añadir `requisitos.no_exigidos: string[]` (por ejemplo `["empadronamiento", "edad"]`). `null` pasa a significar siempre "desconocido" → `DESCONOCIDO` en la calculadora. Solo lo listado en `no_exigidos` cuenta como cumplido. El cambio es barato ahora porque no hay datos reales.

**Decidir antes de la Fase 3.**

## 2. El empadronamiento del Plan Vive es preferencia, no requisito
Desde abril de 2026 ordena la adjudicación sin excluir. `requisitos.empadronamiento` solo expresa requisitos excluyentes.

**Propuesta:** añadir `tipo: "requisito" | "preferencia"`, como ya tiene `edad` con `cupo`. Mientras tanto, el adaptador de Plan Vive debe dejar `empadronamiento` en `null` y describir las prioridades en `requisitos.otros`.

**Decidido (2026-11-27):** solución provisional, sin cambiar el schema. Ver [ADR-002](ADR-002-fuentes-reales.md) §3.

## 3. Un override no llega a la web hasta el siguiente scrape
§3.3 dice que tras corregir `overrides.json` actúa `deploy.yml`, pero `deploy.yml` (§4.2) no ejecuta la fusión: publicaría el `promociones.json` antiguo.

**Propuesta:** ejecutar `vpo merge` en `deploy.yml` antes del build (sin commit). Resolver en la Fase 4.

## 4. Tasa de esfuerzo: base de cálculo
§6.3 R3 divide la renta entre los ingresos introducidos (base imponible). Las convocatorias del Plan Vive citadas en prensa hablan de ingresos **netos** y de renta con gastos incluidos. Confirmar con las bases antes de la Fase 5.

## Ajustes menores ya aplicados en la Fase 1
- `fuentes.json` tiene un campo `prioridad`.
- Hay esquemas adicionales para `data/sources/*.json` y `municipios.json`.
- `state.ultima_ejecucion` admite `null` antes de la primera ejecución.
- La fusión conserva `generado_en` si las promociones no cambian, para no generar diffs diarios.
- Las entradas `VPPB`, `VPPL` y `VPPA` de `programas.json` dejan `iprem_pagas` en `null` porque no está confirmado.
