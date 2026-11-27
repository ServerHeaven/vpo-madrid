// Build time: Datos -> DatosCalculadora, the slim props of the calculator island.
// Requirements are resolved with the same functions as the detail pages (ARCHITECTURE.md §6.2).
import type { Datos } from './contratos';
import type {
  DatosCalculadora,
  Parametro,
  PromocionCalculadora,
  RequisitosCalculadora,
} from './contratos-calculadora';
import { reglasAplicables, resolverRequisitos, type Resuelto } from './requisitos';
import type { Promocion, ReglaPrograma } from './types';

const sinVerificar = (regla: ReglaPrograma | null): boolean => regla !== null && !regla.verificado;

// `regla` is only set for general values, so convocatoria and manual values are never flagged.
const parametro = <T>({ valor, origen, regla }: Resuelto<T>): Parametro<T> => ({
  valor,
  origen,
  sin_verificar: sinVerificar(regla),
});

const opcional = <T>(resuelto: Resuelto<T> | null): Parametro<T> | null =>
  resuelto === null ? null : parametro(resuelto);

/** Weighting factors have no field in the promotion: only programas.json supplies them. */
function coeficientes(
  promo: Promocion,
  programas: ReglaPrograma[],
): RequisitosCalculadora['coeficientes_ponderacion'] {
  const regla = reglasAplicables(promo, programas).find((r) => r.coeficientes_ponderacion !== null);
  if (!regla) return { valor: null, origen: 'desconocido', sin_verificar: false };
  return { valor: regla.coeficientes_ponderacion, origen: regla.tipo, sin_verificar: sinVerificar(regla) };
}

function requisitos(promo: Promocion, programas: ReglaPrograma[]): RequisitosCalculadora {
  const r = resolverRequisitos(promo, programas);
  return {
    ingresos_min_iprem: opcional(r.ingresos_min_iprem),
    ingresos_max_iprem: opcional(r.ingresos_max_iprem),
    ingresos_por_miembros: opcional(r.ingresos_por_miembros),
    iprem_pagas: parametro(r.iprem_pagas),
    iprem_ejercicio: parametro(r.iprem_ejercicio),
    tasa_esfuerzo_max: parametro(r.tasa_esfuerzo_max),
    empadronamiento: parametro(r.empadronamiento),
    edad: parametro(r.edad),
    no_titular_vivienda: parametro(r.no_titular_vivienda),
    coeficientes_ponderacion: coeficientes(promo, programas),
    condiciones: r.condiciones.map(({ texto, origen, regla }) => ({
      texto,
      origen,
      sin_verificar: sinVerificar(regla),
    })),
  };
}

function resumir(promo: Promocion, programas: ReglaPrograma[]): PromocionCalculadora {
  return {
    id: promo.id,
    nombre: promo.nombre,
    operador: promo.operador.nombre,
    municipio_ine: promo.ubicacion.municipio_ine,
    municipio: promo.ubicacion.municipio,
    estado: promo.estado,
    activa_en_fuente: promo.meta.activa_en_fuente,
    tipologias: promo.tipologias.map((t) => ({
      dormitorios: t.dormitorios,
      renta_mensual_eur: t.renta_mensual_eur,
    })),
    requisitos: requisitos(promo, programas),
  };
}

export function construirDatosCalculadora(datos: Datos): DatosCalculadora {
  return {
    generado_en: datos.generado_en,
    promociones: datos.promociones.map((p) => resumir(p, datos.programas)),
    iprem: datos.iprem.map(({ anio, anual_12, anual_14, verificado }) => ({
      anio,
      anual_12,
      anual_14,
      verificado,
    })),
    municipios: datos.municipios.map(({ ine, nombre }) => ({ ine, nombre })),
  };
}
