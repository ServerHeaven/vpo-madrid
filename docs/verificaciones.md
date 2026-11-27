# Verificaciones normativas

Fecha de consulta: 2026-11-27. Revisar al empezar cada fase y cada enero.

## IPREM
| Dato | Resultado | Fuente |
|---|---|---|
| 2023: 600 €/mes, 7.200 € (12 pagas), 8.400 € (14 pagas) | Confirmado, texto leído | [Ley 31/2022, DA 90ª](https://www.boe.es/buscar/act.php?id=BOE-A-2022-22128) |
| 2024-2026: igual | Se deduce de la prórroga de los presupuestos de 2023; no he encontrado norma que cambie el IPREM | [RDL 3/2026](https://www.boe.es/buscar/act.php?id=BOE-A-2026-2548) menciona la prórroga (según resultado de búsqueda, no leído entero) |

**12 o 14 pagas: 14 en vivienda protegida de Madrid** (comprobado en la Fase 5).
- Plan Vive, expreso: «número de veces el IPREM, referido a 14 pagas» ([Decreto 31/2026, BOCM núm. 83 de 09/04/2026](https://bocm.es/boletin/CM_Orden_BOCM/2026/04/09/BOCM-20260409-1.PDF), texto leído).
- Régimen general: el [manual de la calculadora de ingresos](https://www.comunidad.madrid/docs/2026-07/viv_prot_manual_calculadora_irpf_2025.pdf) (junio 2026, texto leído) usa 8.400 € para 2023-2026. Es la cifra de 14 pagas, aunque el manual no escribe «14 pagas».

## Ingresos y coeficientes por número de miembros (Fase 5)
Se parte de la base imponible general y del ahorro de cada miembro y se multiplica por un coeficiente.

| Miembros | 1 | 2 | 3 | 4 | 5 | 6 o más |
|---|---|---|---|---|---|---|
| Régimen general (manual; art. 6 de la Orden 5042/2009, no leído directamente) | 0,800 | 0,800 | 0,776 | 0,744 | 0,704 | 0,700 |
| Plan Vive (Decreto 31/2026) | 0,800 | 0,776 | 0,776 | 0,744 | 0,704 | 0,700 |

Enlace estable para el público: [Vivienda protegida de nueva construcción](https://www.comunidad.madrid/vivienda/vivienda-protegida-nueva-construccion) (desde ahí se descargan el manual y la hoja de cálculo; las rutas de los ficheros llevan fecha).

## Decreto 74/2009 (texto revisado por Decreto 59/2013)
[Texto consolidado](https://noticias.juridicas.com/base_datos/CCAA/ma-d74-2009.html) (arts. 2 y 3 leídos) y [página de la Comunidad](https://www.comunidad.madrid/vivienda/vivienda-protegida-nueva-construccion).

- Arrendamiento: máximo 5,5 IPREM (precio básico) y 7,5 (precio limitado).
- Arrendamiento con opción de compra para jóvenes: máximo 5,5 IPREM y edad no superior a 35 años.
- No ser titular de otra vivienda en España (art. 3.3, con excepciones).
- Ingresos según la base imponible general y del ahorro (página de la Comunidad).
- El decreto no fija ingresos mínimos, empadronamiento general ni tasa de esfuerzo.

## Nuevo Reglamento de VPP
**No publicado en el BOCM ni aprobado** a 2026-11-27, así que no se ha añadido a `programas.json`.

- La [nota oficial de 18/11/2026](https://www.comunidad.madrid/noticias/2026/11/18/comunidad-madrid-tramita-nuevo-reglamento-vivienda-protegida-simplifica-gestiones-recupera-alquiler-opcion-compra) (leída en resumen) dice que se ha pedido el informe de la Comisión Jurídica Asesora, último paso antes de la aprobación. La noticia de prensa que daba por aprobado el texto el 19/11 no se confirma.
- [Borrador de 13/03/2026](https://www.comunidad.madrid/transparencia/sites/default/files/2026_03_13_-_borrador_reglamento_vpp.pdf) (puede cambiar): empadronamiento de 5 años en la Comunidad para alquiler (art. 39), IPREM a 14 pagas y coeficientes iguales a los del Plan Vive (art. 42); las viviendas ya calificadas conservan sus condiciones (DT 2ª); deroga el Decreto 74/2009.
- **Acción:** consultar el BOCM antes de cada fase. Al publicarse, añadir versiones nuevas en `programas.json` con su fecha y cerrar (`vigente_hasta`) las actuales según su régimen transitorio.

## Plan Vive
Comprobado en la Fase 5 sobre el [Decreto 84/2020](https://www.bocm.es/boletin/CM_Orden_BOCM/2020/10/09/BOCM-20201009-1.PDF) y el [Decreto 31/2026](https://bocm.es/boletin/CM_Orden_BOCM/2026/04/09/BOCM-20260409-1.PDF) que lo modifica (texto leído).

- Ingresos ponderados: **mínimo 1,5 IPREM para cualquier tamaño de unidad**; máximo 5,5 (precio básico) o 7,5 (precio limitado) (art. 7.1 c).
- **Tasa de esfuerzo: confirmada en norma.** «Que el importe de la renta anual a abonar no exceda del 35 por 100 de los ingresos netos anuales de la unidad de convivencia» (art. 7.1 d). El decreto no define «ingresos netos» ni dice si la renta incluye gastos. Las bases del lote 3 sí incluyen los gastos repercutidos; solo consta para ese lote.
- No ser titular de otra vivienda en España, con excepciones (art. 7.1 e).
- Empadronamiento o centro de trabajo como orden de preferencia (art. 7.1 f): 5 años en el municipio, después 10 en la Comunidad, después sin mínimo. La disposición transitoria rebaja a 3 años (y 5 en la Comunidad) para promociones terminadas o en obra y solicitantes inscritos antes del 31/12/2026: de ahí la discrepancia con las preguntas frecuentes.
- La exigencia de estar inscrito en el Registro de Demandantes, que figuraba en `programas.json`, no aparece en el decreto, su modificación, las bases leídas ni las preguntas frecuentes: **se ha retirado**.

## Régimen VPPA
Las fichas de EMVS usan VPPA para arrendamiento sin opción de compra, con edades distintas de las que recoge la entrada `VPPA` de `programas.json`. **Pendiente de revisar** (ADR-002, punto A).

## Operadoras (fuentes secundarias, a confirmar en Fase 5)
- ConVive Madrid es la marca del lote que gestiona Sogeviso, no de Avalon.
- Cada operadora del Plan Vive gestiona su propia inscripción.
