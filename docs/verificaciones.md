# Verificaciones normativas

Fecha de consulta: 2026-11-27. Revisar al empezar cada fase y cada enero.

## IPREM
| Dato | Resultado | Fuente |
|---|---|---|
| 2023: 600 €/mes, 7.200 € (12 pagas), 8.400 € (14 pagas) | Confirmado, texto leído | [Ley 31/2022, DA 90ª](https://www.boe.es/buscar/act.php?id=BOE-A-2022-22128) |
| 2024-2026: igual | Se deduce de la prórroga de los presupuestos de 2023; no he encontrado norma que cambie el IPREM | [RDL 3/2026](https://www.boe.es/buscar/act.php?id=BOE-A-2026-2548) menciona la prórroga (según resultado de búsqueda, no leído entero) |

La DA 90ª reserva los 8.400 € a normas que se refieren al salario mínimo en cómputo anual. **Qué cifra (12 o 14 pagas) aplica a la vivienda protegida de Madrid no está confirmado:** el Decreto 74/2009 no lo dice. Pendiente de revisar el manual de la calculadora de ingresos de la Comunidad antes de la Fase 5.

## Decreto 74/2009 (texto revisado por Decreto 59/2013)
[Texto consolidado](https://noticias.juridicas.com/base_datos/CCAA/ma-d74-2009.html) (arts. 2 y 3 leídos) y [página de la Comunidad](https://www.comunidad.madrid/vivienda/vivienda-protegida-nueva-construccion).

- Arrendamiento: máximo 5,5 IPREM (precio básico) y 7,5 (precio limitado).
- Arrendamiento con opción de compra para jóvenes: máximo 5,5 IPREM y edad no superior a 35 años.
- No ser titular de otra vivienda en España (art. 3.3, con excepciones).
- Ingresos según la base imponible general y del ahorro (página de la Comunidad).
- El decreto no fija ingresos mínimos, empadronamiento general ni tasa de esfuerzo.

## Nuevo Reglamento de VPP
**No consta publicado en el BOCM**, así que no se ha añadido a `programas.json`.

- La prensa informa el 19/11/2026 de su paso por el Consejo de Gobierno y de que entrará en vigor al publicarse en el BOCM ([Qué! Madrid](https://www.que.madrid/2026/11/19/vivienda-protegida-madrid-reglamento-600457/)). No he encontrado nota oficial de noviembre ni número de decreto.
- La nota oficial de abril anunciaba para el reglamento 5 años de empadronamiento para alquiler y 10 para compra.
- **Acción:** consultar el BOCM antes de cada fase. Al publicarse, añadir versiones nuevas en `programas.json` con su fecha y cerrar (`vigente_hasta`) las actuales según su régimen transitorio.

## Plan Vive
[Nota oficial de 08/04/2026](https://www.comunidad.madrid/noticias/2026/04/08/reforzado-plan-vive-flexibilizar-requisitos-acceso-agilizar-adjudicacion-viviendas-alquiler-asequible) (modificación del Decreto 84/2020):

- Unidades de dos miembros: 1,5 a 5,5 IPREM (precio básico), 1,5 a 7,5 (precio limitado).
- Empadronamiento como **preferencia**, no como requisito excluyente: 5 años en el municipio, después 10 en la Comunidad, después el resto.
- **Tasa de esfuerzo del 35 %: sin confirmar** en fuente oficial. Sigue como `verificado: false`.
- Pendiente: leer el Decreto 84/2020 consolidado y su modificación.

### Preguntas frecuentes de la página del Plan Vive
[Página oficial](https://www.comunidad.madrid/plan-vive), apartado «Dudas frecuentes», leído el 2026-11-27:

- Esfuerzo: «no se debe destinar más del 35% de los ingresos netos anuales de la Unidad de Convivencia al pago de la renta total anual». **Una fuente oficial sí afirma el 35 %**, referido a ingresos netos (ver ADR-001 §4). `programas.json` sigue con `verificado: false` hasta que se revise a mano.
- Prioridad por empadronamiento o centro de trabajo «con una antigüedad mínima de 3 años». **Discrepa** de la nota de 08/04/2026 (5 años en el municipio). No se publica ningún número.
- Ingresos: remite a «la tabla del IPREM» sin dar cifras.

## Régimen VPPA
Las fichas de EMVS usan VPPA para arrendamiento sin opción de compra, con edades distintas de las que recoge la entrada `VPPA` de `programas.json`. **Pendiente de revisar** (ADR-002, punto A).

## Operadoras (fuentes secundarias, a confirmar en Fase 5)
- ConVive Madrid es la marca del lote que gestiona Sogeviso, no de Avalon.
- Cada operadora del Plan Vive gestiona su propia inscripción.
