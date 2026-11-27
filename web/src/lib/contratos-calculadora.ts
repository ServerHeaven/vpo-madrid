// Contract between the calculator modules (ARCHITECTURE.md §6). Types and constants only.
//   lib/eligibility.ts       pure engine: evaluates DatosCalculadora against EntradaCalculadora
//   lib/datos-calculadora.ts build time: Datos -> DatosCalculadora (§6.2 already resolved)
//   islands/Calculadora.tsx  form and results
import type { EstadoPromocion } from './contratos';
import type { Origen } from './requisitos';
import type { IngresosPorMiembros, Requisitos } from './types';

/** Value of `municipio_empadronamiento` / `municipio_trabajo` for a place outside the Comunidad. */
export const FUERA_DE_LA_COMUNIDAD = 'fuera';

/** What the person types. Never stored, never sent, never put in the URL. null = not given. */
export interface EntradaCalculadora {
  /** Yearly taxable base of the whole household (or its estimate from the gross figure). */
  ingresos_anuales: number;
  /** true when ingresos_anuales comes from estimarBaseImponible. */
  ingresos_estimados: boolean;
  /** Tax year of the income; picks the IPREM unless the bases fix another one. */
  ejercicio: number;
  /** Household size, 1-10. */
  miembros: number;
  /** INE code (28xxx), FUERA_DE_LA_COMUNIDAD or null. */
  municipio_empadronamiento: string | null;
  anios_empadronamiento: number | null;
  municipio_trabajo: string | null;
  anios_trabajo: number | null;
  /** Age of the main applicant. */
  edad: number | null;
  titular_vivienda: boolean | null;
  /** Preference filter, not an eligibility rule. */
  dormitorios_min: number | null;
}

/** A requirement already resolved at build time (§6.2). */
export interface Parametro<T> {
  /** null when unknown or not demanded: `origen` tells them apart. */
  valor: T | null;
  origen: Origen;
  /** true only for a general value (origen "programa" or "regimen") from an unverified entry. */
  sin_verificar: boolean;
}

export interface CondicionCalculadora {
  texto: string;
  origen: 'convocatoria' | 'programa' | 'regimen';
  sin_verificar: boolean;
}

export interface RequisitosCalculadora {
  /** Both flat limits are null when a table by household size exists: it prevails. */
  ingresos_min_iprem: Parametro<number> | null;
  ingresos_max_iprem: Parametro<number> | null;
  ingresos_por_miembros: Parametro<IngresosPorMiembros[]> | null;
  iprem_pagas: Parametro<12 | 14>;
  iprem_ejercicio: Parametro<number>;
  tasa_esfuerzo_max: Parametro<number>;
  empadronamiento: Parametro<NonNullable<Requisitos['empadronamiento']>>;
  edad: Parametro<NonNullable<Requisitos['edad']>>;
  no_titular_vivienda: Parametro<boolean>;
  /** Household size -> factor applied to the income; only programas.json supplies it. */
  coeficientes_ponderacion: Parametro<Record<string, number>>;
  /** "You must also meet" list (R9). */
  condiciones: CondicionCalculadora[];
}

export interface TipologiaCalculadora {
  dormitorios: number | null;
  renta_mensual_eur: number | null;
}

export interface PromocionCalculadora {
  id: string;
  nombre: string;
  operador: string; // display name
  municipio_ine: string;
  municipio: string;
  estado: EstadoPromocion;
  activa_en_fuente: boolean;
  tipologias: TipologiaCalculadora[];
  requisitos: RequisitosCalculadora;
}

export interface IpremAnual {
  anio: number;
  anual_12: number;
  anual_14: number;
  verificado: boolean;
}

export interface Municipio {
  ine: string;
  nombre: string;
}

/** Everything the island receives as props: it makes no requests of its own. */
export interface DatosCalculadora {
  generado_en: string;
  promociones: PromocionCalculadora[];
  iprem: IpremAnual[];
  municipios: Municipio[];
}

// ---------------------------------------------------------------- results

export type EstadoRegla = 'CUMPLE' | 'NO_CUMPLE' | 'DESCONOCIDO' | 'INFORMATIVO';

/** R1-R7 of §6.3, in this order. R8 has no data in the schema; R9 is `condiciones`. */
export type IdRegla =
  | 'ingresos_max' // R1
  | 'ingresos_min' // R2
  | 'tasa_esfuerzo' // R3
  | 'empadronamiento' // R4
  | 'edad' // R5
  | 'titularidad' // R6
  | 'estado'; // R7

export interface ResultadoRegla {
  id: IdRegla;
  estado: EstadoRegla;
  /** Readable sentence in Spanish. */
  explicacion: string;
  /** Where the parameter came from; null for rules without one (estado). */
  origen: Origen | null;
  /** The parameter is a general value from an unverified entry: show the badge. */
  sin_verificar: boolean;
}

export interface ResultadoTipologia {
  dormitorios: number | null;
  renta_mensual_eur: number | null;
  /** Effort-rate check for this dwelling type. */
  estado: 'CUMPLE' | 'NO_CUMPLE' | 'DESCONOCIDO';
  /** renta × 12 / tasa; null when either is unknown. */
  ingreso_minimo_anual: number | null;
}

export type Veredicto = 'elegible' | 'posiblemente' | 'no_elegible';

export interface ResultadoPromocion {
  promocion: PromocionCalculadora;
  veredicto: Veredicto;
  reglas: ResultadoRegla[];
  tipologias: ResultadoTipologia[];
  /** Explanation of the first NO_CUMPLE rule; null otherwise. */
  motivo_no_elegible: string | null;
  /** Warnings about the calculation itself, e.g. IPREM of a missing year. */
  avisos: string[];
}

export interface OpcionesEvaluacion {
  /** R7: promotions "finalizada" are left out unless true. */
  mostrarFinalizadas: boolean;
}

// ---------------------------------------------------------------- signatures of lib/eligibility.ts

export interface IpremAplicado {
  importe: number;
  anio: number;
  pagas: 12 | 14;
  /** true when the requested year is not in the table and the latest one was used. */
  sustituido: boolean;
}

export type IpremAplicable = (tabla: IpremAnual[], ejercicio: number, pagas: 12 | 14) => IpremAplicado;

/** gross − 6.35 % social security − 2 000 €, never below 0, rounded to cents (§6.1). */
export type EstimarBaseImponible = (brutoAnual: number) => number;

export type EvaluarPromocion = (
  promocion: PromocionCalculadora,
  entrada: EntradaCalculadora,
  iprem: IpremAnual[],
) => ResultadoPromocion;

/** Evaluates, applies R7's exclusion and the bedroom preference, and sorts (§6.3). */
export type EvaluarTodas = (
  promociones: PromocionCalculadora[],
  entrada: EntradaCalculadora,
  iprem: IpremAnual[],
  opciones: OpcionesEvaluacion,
) => ResultadoPromocion[];
