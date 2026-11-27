// Human labels for the enums of data/schema.
import type { Disponibilidad, EstadoPromocion, Modalidad, Programa, Regimen } from './contratos';
import type { EstadoFuente, Operador } from './types';

export const SIN_DATO = 'Dato no disponible: consulta las bases';

export const ESTADOS: Record<EstadoPromocion, string> = {
  proxima: 'Próximamente',
  inscripcion_abierta: 'Inscripción abierta',
  inscripcion_cerrada: 'Inscripción cerrada',
  sorteo_adjudicacion: 'En sorteo o adjudicación',
  lista_espera_abierta: 'Lista de espera abierta',
  finalizada: 'Finalizada',
  desconocido: 'Estado no disponible',
};

export const REGIMENES: Record<Regimen, string> = {
  VPPB: 'VPPB · precio básico',
  VPPL: 'VPPL · precio limitado',
  VPPA: 'VPPA',
  VPO: 'VPO',
  ASEQUIBLE_NO_CALIFICADA: 'Alquiler asequible no calificado',
  DESCONOCIDO: 'Régimen no disponible',
};

export const PROGRAMAS: Record<NonNullable<Programa>, string> = {
  PLAN_VIVE: 'Plan Vive',
  EMVS_MADRID: 'EMVS Madrid',
  EMV_MUNICIPAL: 'Empresa municipal de vivienda',
  AVS_CAM: 'Agencia de Vivienda Social',
  COOPERATIVA: 'Cooperativa',
  PROMOTOR_PRIVADO: 'Promotor privado',
  OTRO: 'Otro programa',
};

export const MODALIDADES: Record<NonNullable<Modalidad>, string> = {
  alquiler: 'Alquiler',
  alquiler_opcion_compra: 'Alquiler con opción de compra',
};

export const DISPONIBILIDADES: Record<Disponibilidad, string> = {
  incluido: 'Incluido',
  opcional: 'Opcional',
  no: 'No',
  desconocido: 'No consta',
};

export const TIPOS_OPERADOR: Record<Operador['tipo'], string> = {
  publico_autonomico: 'Público autonómico',
  publico_municipal: 'Público municipal',
  privado_concesionario: 'Privado concesionario',
  cooperativa: 'Cooperativa',
  otro: 'Otro',
};

export const ESTADOS_FUENTE: Record<EstadoFuente['estado'], string> = {
  ok: 'Correcta',
  degradado: 'Degradada',
  error: 'Con error',
};

/** 0 bedrooms is a studio. */
export function etiquetaDormitorios(n: number | null): string {
  if (n === null) return 'Dormitorios no disponibles';
  if (n === 0) return 'Estudio';
  return n === 1 ? '1 dormitorio' : `${n} dormitorios`;
}
