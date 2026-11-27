// Shared contracts between modules. Domain names in Spanish, as in data/schema.
import type {
  FuentesFile,
  IpremFile,
  MunicipiosFile,
  OverridesFile,
  Promocion,
  ReglaPrograma,
  State,
} from './types';

export type Regimen = Promocion['regimen'];
export type Programa = Promocion['programa'];
export type Modalidad = Promocion['modalidad'];
export type EstadoPromocion = Promocion['estado'];
export type Disponibilidad = Promocion['tipologias'][number]['garaje']['disponibilidad'];
export type Fuente = FuentesFile['fuentes'][number];

/** Everything the pages need, already validated against data/schema. */
export interface Datos {
  generado_en: string;
  promociones: Promocion[];
  state: State;
  fuentes: Fuente[];
  programas: ReglaPrograma[];
  overrides: OverridesFile;
  iprem: IpremFile['valores'];
  municipios: MunicipiosFile['municipios'];
}

/** Slim view of a promotion: only what the search page needs (ARCHITECTURE.md §7.2). */
export interface IndiceTipologia {
  dormitorios: number | null;
  renta_mensual_eur: number | null;
  renta_mensual_max_eur: number | null;
  garaje: Disponibilidad;
  trastero: Disponibilidad;
}

export interface IndiceItem {
  id: string;
  nombre: string;
  operador: string; // display name
  regimen: Regimen;
  programa: Programa;
  modalidad: Modalidad;
  estado: EstadoPromocion;
  activa_en_fuente: boolean;
  municipio_ine: string;
  municipio: string;
  distrito: string | null;
  viviendas_total: number | null;
  tipologias: IndiceTipologia[];
  inscripcion_fin: string | null; // YYYY-MM-DD
  primera_deteccion: string; // YYYY-MM-DD
}

export interface Indice {
  schema_version: 1;
  generado_en: string;
  promociones: IndiceItem[];
}
