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
