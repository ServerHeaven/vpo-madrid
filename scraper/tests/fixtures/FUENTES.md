# Procedencia de las fixtures

Documentos de terceros usados solo como material de prueba. Pertenecen a sus autores y **no** están cubiertos por la licencia del código.

Todas se descargaron el **2026-11-27** y se revisaron antes de añadirlas: no contienen listados de solicitantes o adjudicatarios, ni nombres o DNI de particulares.

## EMVS Madrid

Recorte común: solo `<main>`, dentro de un esqueleto mínimo; sin scripts, estilos, `<link>`, `<img>`, galerías de miniaturas, menú oculto de SharePoint, atributos `style`/`data-bg` ni líneas en blanco. Los comentarios HTML se conservan a propósito: uno contiene un botón «Inscríbete» retirado que el adaptador debe ignorar. En las fichas, los valores de «Proyecto» y «Empresa constructora» se sustituyen por «(omitido)» porque nombran a particulares.

| Fichero (`html/`) | URL de origen | Recorte |
|---|---|---|
| `emvs_listado_en_proyecto_y_obra.html` | https://www.emvs.es/nuestras-promociones/en-proyecto-y-obra | común |
| `emvs_sorteo.html` | https://www.emvs.es/Vivienda/SorteoPromocion | común |
| `emvs_ficha_il1.html` | https://www.emvs.es/Proyectos/Promociones/Paginas/IL1.aspx | común + nombres omitidos |
| `emvs_ficha_af6.html` | https://www.emvs.es/Proyectos/Promociones/Paginas/AF6.aspx | común + nombres omitidos |
| `emvs_ficha_canav10.html` | https://www.emvs.es/Proyectos/Promociones/Paginas/CANAV10.aspx | común + nombres omitidos |
| `emvs_ficha_v71.html` | https://www.emvs.es/Proyectos/Promociones/Paginas/V71.aspx | común + nombres omitidos |

## Plan Vive

| Fichero (`html/`) | URL de origen | Recorte |
|---|---|---|
| `planvive_2026-11-27.html` | https://www.comunidad.madrid/plan-vive | sin `script`, `style`, `noscript`, `svg` (incluido el mapa), `picture`/`img`, `link`, formularios, cabecera, pie, comentarios ni líneas en blanco (575 KB → 82 KB); el resultado del adaptador es idéntico al de la descarga completa |

## PDF de bases y anuncios (`pdf/`)

Descargados el **2026-11-27**, sin modificar (cada fichero es la descarga byte a byte). Se revisaron todas sus páginas, metadatos y firmas: no contienen listados de solicitantes, admitidos, excluidos o adjudicatarios, DNI/NIE ni formularios rellenados. Pertenecen a sus editores. Los golden de `golden/pdf/` están escritos a mano a partir de cada documento.

Algunos identifican a quien firma el documento por razón de su cargo, sin DNI (columna «Firmante con nombre»). Decisión (2026-11-27): quien firma por un cargo público no se considera «particular»; los documentos firmados por representantes de empresas privadas no se incluyen.

| Fichero (`pdf/`) | URL de origen | Firmante con nombre |
|---|---|---|
| `emvs_iberia_loreto_01.pdf` | https://www.emvs.es/Vivienda/SorteoPromocion/Documents/Bases%20reguladoras%20del%20Programa%20Iberia%20Loreto.pdf | consejera delegada de EMVS (sello de firma al pie) |
| `emvs_reviva_madrid.pdf` | https://www.emvs.es/Alquiler/Reviva/Documents/Bases%20reguladoras%20del%20Programa%20Reviva%20Madrid%20(4%20dic%202023).pdf | no |
| `rivas_emv_83_jovenes.pdf` | https://emv.rivasciudad.es/wp-content/uploads/2025/05/A-BASES-DE-ADJUDICACION-83-VIVIENDAS-EN-REGIMEN-DE-ALQUILER.pdf | no (el metadato «autor» es un nombre de usuario) |
| `planvive_lote5_navalcarnero.pdf` | https://vivaspacesmadrid.com/wp-content/uploads/BASES-ADJUDICACION.pdf | no |
| `planvive_lote5_navalcarnero_2026.pdf` | https://vivaspacesmadrid.com/wp-content/uploads/2026/02/260202-NAVALCARNERO-BASES-ADJUDICACION.pdf | no |
| `bocm_planvive_moralzarzal.pdf` | https://bocm.es/boletin/CM_Orden_BOCM/2026/05/27/BOCM-20260527-92.PDF | no |
| `bocm_planvive_arganda.pdf` | https://www.bocm.es/boletin/CM_Orden_BOCM/2026/03/03/BOCM-20260303-80.PDF | no |
| `bocm_majadahonda_ro8.pdf` | https://www.bocm.es/boletin/CM_Orden_BOCM/2025/10/22/BOCM-20251022-15.PDF | directora general de la Comunidad de Madrid |
| `bocm_pozuelo_humera.pdf` | https://www.bocm.es/boletin/CM_Orden_BOCM/2022/10/18/BOCM-20221018-72.PDF | concejal secretario de la Junta de Gobierno |
| `bocm_morata_tajuna.pdf` | https://www.bocm.es/boletin/CM_Orden_BOCM/2016/08/01/BOCM-20160801-41.PDF | alcalde |
