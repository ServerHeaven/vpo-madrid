// Builds the slim index used by the search page.
import type { Indice, IndiceItem } from './contratos';
import type { Promocion } from './types';

function resumir(p: Promocion): IndiceItem {
  return {
    id: p.id,
    nombre: p.nombre,
    operador: p.operador.nombre,
    regimen: p.regimen,
    programa: p.programa,
    modalidad: p.modalidad,
    estado: p.estado,
    activa_en_fuente: p.meta.activa_en_fuente,
    municipio_ine: p.ubicacion.municipio_ine,
    municipio: p.ubicacion.municipio,
    distrito: p.ubicacion.distrito,
    viviendas_total: p.viviendas_total,
    tipologias: p.tipologias.map((t) => ({
      dormitorios: t.dormitorios,
      renta_mensual_eur: t.renta_mensual_eur,
      renta_mensual_max_eur: t.renta_mensual_max_eur,
      garaje: t.garaje.disponibilidad,
      trastero: t.trastero.disponibilidad,
    })),
    inscripcion_fin: p.fechas.inscripcion_fin,
    primera_deteccion: p.meta.primera_deteccion,
  };
}

export function construirIndice(promociones: Promocion[], generadoEn: string): Indice {
  return { schema_version: 1, generado_en: generadoEn, promociones: promociones.map(resumir) };
}
