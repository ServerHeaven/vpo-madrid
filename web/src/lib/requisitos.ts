// Display-only resolution of each requirement and where it comes from (ARCHITECTURE.md §6.2).
// Pure. It does not evaluate eligibility.
import { formatNumero } from './format';
import type { IngresosPorMiembros, Procedencia, Promocion, ReglaPrograma, Requisitos } from './types';

export type Origen = 'convocatoria' | 'manual' | 'programa' | 'regimen' | 'no_exigido' | 'desconocido';

export const ORIGENES: Record<Origen, string> = {
  convocatoria: 'De la convocatoria',
  manual: 'Corrección manual',
  programa: 'Valor general del programa, comprueba las bases',
  regimen: 'Valor general del régimen, comprueba las bases',
  no_exigido: 'Consta que no se exige',
  desconocido: 'Desconocido',
};

export interface Correccion {
  puntero: string;
  motivo: string | null;
}

export interface Resuelto<T> {
  /** null when unknown or not demanded: `origen` tells them apart. */
  valor: T | null;
  origen: Origen;
  /** The programas.json entry that supplied a general value. */
  regla: ReglaPrograma | null;
  correcciones: Correccion[];
  pendiente: boolean;
  /** How the convocatoria value was obtained; null for general or unknown values. */
  procedencia: Procedencia | null;
}

export interface Condicion {
  texto: string;
  origen: 'convocatoria' | 'programa' | 'regimen';
  regla: ReglaPrograma | null;
}

export interface RequisitosResueltos {
  /** null when a table by household size exists: it prevails over the flat limits. */
  ingresos_min_iprem: Resuelto<number> | null;
  ingresos_max_iprem: Resuelto<number> | null;
  ingresos_por_miembros: Resuelto<IngresosPorMiembros[]> | null;
  iprem_pagas: Resuelto<12 | 14>;
  iprem_ejercicio: Resuelto<number>;
  tasa_esfuerzo_max: Resuelto<number>;
  empadronamiento: Resuelto<NonNullable<Requisitos['empadronamiento']>>;
  edad: Resuelto<NonNullable<Requisitos['edad']>>;
  no_titular_vivienda: Resuelto<boolean>;
  condiciones: Condicion[];
  correccionesCondiciones: Correccion[];
}

const cubre = (ancestro: string, puntero: string): boolean =>
  puntero === ancestro || puntero.startsWith(`${ancestro}/`);

const solapan = (a: string, b: string): boolean => cubre(a, b) || cubre(b, a);

/** Manual corrections touching a field: the field itself, an ancestor or something inside it. */
export function correccionesDe(meta: Promocion['meta'], puntero: string): Correccion[] {
  return meta.campos_override
    .filter((p) => solapan(p, puntero))
    .map((p) => ({ puntero: p, motivo: meta.procedencia[p]?.evidencia ?? null }));
}

export const estaPendiente = (meta: Promocion['meta'], puntero: string): boolean =>
  meta.campos_pendientes.some((p) => solapan(p, puntero));

/** Provenance recorded for a field or for the closest object that contains it. */
export function procedenciaDe(meta: Promocion['meta'], puntero: string): Procedencia | null {
  for (let p = puntero; p !== ''; p = p.slice(0, p.lastIndexOf('/'))) {
    const encontrada = meta.procedencia[p];
    if (encontrada) return encontrada;
  }
  return null;
}

export const fechaReferencia = (promo: Promocion): string =>
  promo.fechas.inscripcion_inicio ?? promo.meta.primera_deteccion;

/** The version of an entry in force on a date (both ends inclusive, null = open). */
export function reglaVigente(
  programas: ReglaPrograma[],
  tipo: ReglaPrograma['tipo'],
  clave: string,
  fecha: string,
): ReglaPrograma | null {
  const vigentes = programas.filter(
    (r) =>
      r.tipo === tipo &&
      r.clave === clave &&
      (r.vigente_desde === null || r.vigente_desde <= fecha) &&
      (r.vigente_hasta === null || r.vigente_hasta >= fecha),
  );
  vigentes.sort((a, b) => (b.vigente_desde ?? '').localeCompare(a.vigente_desde ?? ''));
  return vigentes[0] ?? null;
}

/** Entries that may supply defaults, in priority order: programme first, then régimen. */
export function reglasAplicables(promo: Promocion, programas: ReglaPrograma[]): ReglaPrograma[] {
  const fecha = fechaReferencia(promo);
  // ADR-002 A: the VPPA entry describes rent with an option to buy, while some operators call plain
  // rent "VPPA". It only applies when the promotion is known to carry that option.
  const regimenAplicable = promo.regimen !== 'VPPA' || promo.modalidad === 'alquiler_opcion_compra';
  return [
    promo.programa ? reglaVigente(programas, 'programa', promo.programa, fecha) : null,
    regimenAplicable ? reglaVigente(programas, 'regimen', promo.regimen, fecha) : null,
  ].filter((r): r is ReglaPrograma => r !== null);
}

type Clave = Exclude<keyof Requisitos, 'no_exigidos' | 'otros'>;
type ClaveGeneral = Extract<Clave, keyof ReglaPrograma>;

export function resolverRequisitos(promo: Promocion, programas: ReglaPrograma[]): RequisitosResueltos {
  const { meta, requisitos } = promo;
  const reglas = reglasAplicables(promo, programas);

  function resolver<T>(clave: Clave, general?: ClaveGeneral): Resuelto<T> {
    const puntero = `/requisitos/${clave}`;
    const correcciones = correccionesDe(meta, puntero);
    const base = { correcciones, pendiente: estaPendiente(meta, puntero), regla: null, procedencia: null };
    // Only an explicit entry in no_exigidos means "not demanded"; a bare null never does.
    if ((requisitos.no_exigidos as string[]).includes(clave)) {
      const declaradas = correccionesDe(meta, '/requisitos/no_exigidos').filter(
        (c) => !correcciones.some((o) => o.puntero === c.puntero),
      );
      return { ...base, correcciones: [...correcciones, ...declaradas], valor: null, origen: 'no_exigido' };
    }
    const propio = requisitos[clave] as T | null;
    if (propio !== null) {
      const origen = correcciones.length > 0 ? 'manual' : 'convocatoria';
      return { ...base, valor: propio, origen, procedencia: procedenciaDe(meta, puntero) };
    }
    if (general) {
      const regla = reglas.find((r) => r[general] !== null);
      if (regla) return { ...base, valor: regla[general] as T, origen: regla.tipo, regla };
    }
    return { ...base, valor: null, origen: 'desconocido' };
  }

  const tabla = requisitos.ingresos_por_miembros?.length
    ? resolver<IngresosPorMiembros[]>('ingresos_por_miembros')
    : null;

  const condiciones: Condicion[] = requisitos.otros.map((texto) => ({
    texto,
    origen: 'convocatoria',
    regla: null,
  }));
  for (const regla of reglas) {
    for (const texto of regla.requisitos_no_comprobables) {
      if (!condiciones.some((c) => c.texto === texto)) condiciones.push({ texto, origen: regla.tipo, regla });
    }
  }

  return {
    ingresos_min_iprem: tabla ? null : resolver('ingresos_min_iprem', 'ingresos_min_iprem'),
    ingresos_max_iprem: tabla ? null : resolver('ingresos_max_iprem', 'ingresos_max_iprem'),
    ingresos_por_miembros: tabla,
    iprem_pagas: resolver('iprem_pagas', 'iprem_pagas'),
    iprem_ejercicio: resolver('iprem_ejercicio'),
    tasa_esfuerzo_max: resolver('tasa_esfuerzo_max', 'tasa_esfuerzo_max'),
    empadronamiento: resolver('empadronamiento', 'empadronamiento'),
    edad: resolver('edad', 'edad'),
    no_titular_vivienda: resolver('no_titular_vivienda'),
    condiciones,
    correccionesCondiciones: correccionesDe(meta, '/requisitos/otros'),
  };
}

export const textoIngresosMax = (veces: number): string => `Hasta ${formatNumero(veces)} veces el IPREM`;
export const textoIngresosMin = (veces: number): string => `Desde ${formatNumero(veces)} veces el IPREM`;
export const textoTasa = (tasa: number): string => `Máximo ${formatNumero(tasa * 100)} % de los ingresos`;
export const textoTitularidad = (exigido: boolean): string =>
  exigido ? 'No ser titular de otra vivienda' : 'No se exige carecer de otra vivienda';

export function textoMiembros(fila: IngresosPorMiembros): string {
  const { miembros_desde: desde, miembros_hasta: hasta } = fila;
  if (hasta === null) return `${desde} o más`;
  return hasta === desde ? `${desde}` : `De ${desde} a ${hasta}`;
}

/** null when the entry carries no limit at all. */
export function textoEdad(edad: NonNullable<Requisitos['edad']>): string | null {
  const { min, max, tipo } = edad;
  let tramo: string;
  if (min !== null && max !== null) tramo = `De ${min} a ${max} años`;
  else if (min !== null) tramo = `Desde ${min} años`;
  else if (max !== null) tramo = `Hasta ${max} años`;
  else return null;
  return tipo === 'cupo' ? `Cupo reservado (no excluye): ${tramo.toLowerCase()}` : tramo;
}

export function textoEmpadronamiento(
  padron: NonNullable<Requisitos['empadronamiento']>,
  promo: Promocion,
): string {
  let lugar = 'la Comunidad de Madrid';
  if (padron.ambito === 'municipio') {
    if (padron.municipio_ine === null) lugar = 'el municipio que indiquen las bases';
    else if (padron.municipio_ine === promo.ubicacion.municipio_ine) lugar = promo.ubicacion.municipio;
    else lugar = `el municipio con código INE ${padron.municipio_ine}`;
  }
  const partes = [`Estar empadronado en ${lugar}`];
  if (padron.anios_min === null) partes.push('antigüedad mínima no disponible');
  else if (padron.anios_min > 0) {
    const unidad = padron.anios_min === 1 ? 'año' : 'años';
    const seguido = padron.ininterrumpido ? ' de forma ininterrumpida' : '';
    partes.push(`al menos ${formatNumero(padron.anios_min)} ${unidad}${seguido}`);
  }
  if (padron.alternativa_trabajo) partes.push('o trabajar allí');
  return partes.join(', ');
}
