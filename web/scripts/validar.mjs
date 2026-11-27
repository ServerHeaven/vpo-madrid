// Validation of data/ against data/schema, shared by the build (src/lib/data.ts) and the CLI.
// Plain ESM so that `node scripts/validate-data.mjs` needs no build step.
// Cross-file checks that JSON Schema cannot express stay in `python -m vpo validate`.
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

// File inside data/ → schema name. Every data/sources/*.json uses "source".
const ARCHIVOS = {
  'promociones.json': 'promociones',
  'state.json': 'state',
  'overrides.json': 'overrides',
  'iprem.json': 'iprem',
  'programas.json': 'programas',
  'municipios.json': 'municipios',
  'fuentes.json': 'fuentes',
};

/** Walks up from `desde` to the first folder that holds data/schema and returns that data/ folder. */
export function encontrarDataDir(desde = process.cwd()) {
  let carpeta = resolve(desde);
  for (;;) {
    const candidata = join(carpeta, 'data');
    const esquemas = join(candidata, 'schema');
    if (existsSync(esquemas) && statSync(esquemas).isDirectory()) return candidata;
    const superior = dirname(carpeta);
    if (superior === carpeta) throw new Error(`No encuentro data/schema a partir de ${resolve(desde)}`);
    carpeta = superior;
  }
}

const leerJson = (ruta) => JSON.parse(readFileSync(ruta, 'utf8'));

function compilarEsquemas(dirEsquemas) {
  // strict: false keeps parity with the Python validator, which accepts the same schemas as they are.
  const ajv = new Ajv2020({ allErrors: true, strict: false });
  addFormats(ajv);
  const esquemas = readdirSync(dirEsquemas)
    .filter((f) => f.endsWith('.schema.json'))
    .map((f) => [f.replace('.schema.json', ''), leerJson(join(dirEsquemas, f))]);
  // All are registered before compiling any, so relative $ref between files resolves.
  for (const [, esquema] of esquemas) ajv.addSchema(esquema);
  const ids = Object.fromEntries(esquemas.map(([nombre, esquema]) => [nombre, esquema.$id]));
  return (nombre) => {
    const validar = ids[nombre] && ajv.getSchema(ids[nombre]);
    if (!validar) throw new Error(`Falta el schema ${nombre}.schema.json en ${dirEsquemas}`);
    return validar;
  };
}

function mensaje({ keyword, params, message, propertyName }) {
  const clave = propertyName === undefined ? '' : `clave "${propertyName}": `;
  const detalle = {
    required: () => `falta la propiedad obligatoria "${params.missingProperty}"`,
    additionalProperties: () => `propiedad no permitida "${params.additionalProperty}"`,
    type: () => `debe ser de tipo ${[params.type].flat().join(' o ')}`,
    enum: () => `debe ser uno de: ${params.allowedValues.map((v) => JSON.stringify(v)).join(', ')}`,
    const: () => `debe ser ${JSON.stringify(params.allowedValue)}`,
    format: () => `no tiene el formato "${params.format}"`,
    pattern: () => `no cumple el patrón ${params.pattern}`,
    minimum: () => `debe ser ≥ ${params.limit}`,
    maximum: () => `debe ser ≤ ${params.limit}`,
    exclusiveMinimum: () => `debe ser > ${params.limit}`,
    minLength: () => `debe tener al menos ${params.limit} caracteres`,
    maxLength: () => `debe tener como máximo ${params.limit} caracteres`,
    minItems: () => `debe tener al menos ${params.limit} elementos`,
    maxItems: () => `debe tener como máximo ${params.limit} elementos`,
    uniqueItems: () => 'tiene elementos repetidos',
    propertyNames: () => `nombre de propiedad no válido "${params.propertyName}"`,
  }[keyword];
  return clave + (detalle ? detalle() : message);
}

/**
 * Reads and validates every data file.
 * @returns {{ errores: string[], contenidos: Record<string, any> }} contents keyed by path inside data/.
 */
export function validarDatos(dataDir) {
  const validador = compilarEsquemas(join(dataDir, 'schema'));
  const dirFuentes = join(dataDir, 'sources');
  const fuentes = existsSync(dirFuentes)
    ? readdirSync(dirFuentes)
        .filter((f) => f.endsWith('.json'))
        .sort()
        .map((f) => [`sources/${f}`, 'source'])
    : [];

  const errores = [];
  const contenidos = {};
  for (const [nombre, esquema] of [...Object.entries(ARCHIVOS), ...fuentes]) {
    const ruta = join(dataDir, nombre);
    if (!existsSync(ruta)) {
      errores.push(`${nombre}: no existe`);
      continue;
    }
    let contenido;
    try {
      contenido = leerJson(ruta);
    } catch (error) {
      errores.push(`${nombre}: no es JSON válido (${error.message})`);
      continue;
    }
    const validar = validador(esquema);
    if (!validar(contenido)) {
      errores.push(...validar.errors.map((e) => `${nombre}: ${e.instancePath || '/'}: ${mensaje(e)}`));
    }
    contenidos[nombre] = contenido;
  }
  return { errores, contenidos };
}
