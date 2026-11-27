// Build-time data access: loads ../data/*.json and validates it with Ajv.
import { resolve } from 'node:path';
import { encontrarDataDir as buscarDataDir, validarDatos } from '../../scripts/validar.mjs';
import type { Datos } from './contratos';
import type {
  FuentesFile,
  IpremFile,
  MunicipiosFile,
  OverridesFile,
  ProgramasFile,
  PromocionesFile,
  State,
} from './types';

const ERRORES_MOSTRADOS = 20;
const cache = new Map<string, Datos>();

/** Walks up from `desde` (default: process.cwd()) to the folder that holds data/schema. */
export function encontrarDataDir(desde?: string): string {
  return buscarDataDir(desde);
}

/** Validated data, cached per directory. Throws (failing the build) if anything does not validate. */
export function cargarDatos(dataDir?: string): Datos {
  const carpeta = resolve(dataDir ?? encontrarDataDir());
  const guardados = cache.get(carpeta);
  if (guardados) return guardados;

  const { errores, contenidos } = validarDatos(carpeta);
  if (errores.length > 0) {
    const resto = errores.length - ERRORES_MOSTRADOS;
    const lista = errores.slice(0, ERRORES_MOSTRADOS).map((e) => `  ${e}`);
    if (resto > 0) lista.push(`  (y ${resto} más)`);
    throw new Error(`Los datos de ${carpeta} no cumplen el schema:\n${lista.join('\n')}`);
  }

  // The casts are safe: each file has just been validated against the schema its type comes from.
  const promociones = contenidos['promociones.json'] as PromocionesFile;
  const datos: Datos = {
    generado_en: promociones.generado_en,
    promociones: promociones.promociones,
    state: contenidos['state.json'] as State,
    fuentes: (contenidos['fuentes.json'] as FuentesFile).fuentes,
    programas: (contenidos['programas.json'] as ProgramasFile).programas,
    overrides: contenidos['overrides.json'] as OverridesFile,
    iprem: (contenidos['iprem.json'] as IpremFile).valores,
    municipios: (contenidos['municipios.json'] as MunicipiosFile).municipios,
  };
  cache.set(carpeta, datos);
  return datos;
}
