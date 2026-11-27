import { spawnSync } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { cargarDatos, encontrarDataDir } from '../src/lib/data';

const real = encontrarDataDir();
const temporales: string[] = [];

/** A private copy of the real data/ that a test can break. */
function copia(): string {
  const raiz = mkdtempSync(join(tmpdir(), 'vpo-datos-'));
  temporales.push(raiz);
  const destino = join(raiz, 'data');
  cpSync(real, destino, { recursive: true });
  return destino;
}

function editar(carpeta: string, nombre: string, cambio: (contenido: any) => void): void {
  const ruta = join(carpeta, nombre);
  const contenido = JSON.parse(readFileSync(ruta, 'utf8'));
  cambio(contenido);
  writeFileSync(ruta, JSON.stringify(contenido));
}

const validarPorConsola = (carpeta: string) =>
  spawnSync(process.execPath, ['scripts/validate-data.mjs', carpeta], { encoding: 'utf8' });

afterEach(() => {
  for (const carpeta of temporales.splice(0)) rmSync(carpeta, { recursive: true, force: true });
});

describe('cargarDatos', () => {
  it('carga y valida los datos reales', () => {
    const datos = cargarDatos();
    expect(datos.promociones.length).toBeGreaterThan(0);
    expect(datos.fuentes.length).toBeGreaterThan(0);
    expect(datos.programas.length).toBeGreaterThan(0);
    expect(datos.state.schema_version).toBe(1);
    expect(datos.overrides.schema_version).toBe(1);
    expect(datos.generado_en).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(cargarDatos(real)).toBe(datos); // cached per directory
  });

  it('encuentra data/ desde una carpeta anidada', () => {
    expect(encontrarDataDir(join(real, 'sources'))).toBe(real);
  });

  it('falla con un mensaje claro si no hay data/schema', () => {
    const vacia = mkdtempSync(join(tmpdir(), 'vpo-vacia-'));
    temporales.push(vacia);
    expect(() => encontrarDataDir(vacia)).toThrow(/No encuentro data\/schema/);
  });

  it('falla indicando fichero y ruta JSON cuando un dato no cumple el schema', () => {
    const carpeta = copia();
    editar(carpeta, 'promociones.json', (c) => {
      c.promociones[0].estado = 'abierta';
      delete c.promociones[0].viviendas_total;
    });
    expect(() => cargarDatos(carpeta)).toThrow(/promociones\.json: \/promociones\/0\/estado: debe ser uno de/);
    expect(() => cargarDatos(carpeta)).toThrow(/falta la propiedad obligatoria "viviendas_total"/);
  });

  it('también valida las fuentes y los ficheros manuales', () => {
    const carpeta = copia();
    editar(carpeta, 'sources/plan-vive-cam.json', (c) => (c.sobra = 1));
    editar(carpeta, 'iprem.json', (c) => (c.valores[0].mensual = 'seiscientos'));
    expect(() => cargarDatos(carpeta)).toThrow(/sources\/plan-vive-cam\.json: \/: propiedad no permitida "sobra"/);
    expect(() => cargarDatos(carpeta)).toThrow(/iprem\.json: \/valores\/0\/mensual: debe ser de tipo number/);
  });

  it('falla si un fichero falta o no es JSON', () => {
    const carpeta = copia();
    rmSync(join(carpeta, 'state.json'));
    writeFileSync(join(carpeta, 'fuentes.json'), '{');
    expect(() => cargarDatos(carpeta)).toThrow(/state\.json: no existe/);
    expect(() => cargarDatos(carpeta)).toThrow(/fuentes\.json: no es JSON válido/);
  });
});

describe('validate-data', () => {
  it('termina bien con los datos reales', () => {
    const resultado = validarPorConsola(real);
    expect(resultado.stderr).toBe('');
    expect(resultado.status).toBe(0);
    expect(resultado.stdout).toContain('data/ es válido');
  });

  it('termina con error si algo no valida', () => {
    const carpeta = copia();
    editar(carpeta, 'municipios.json', (c) => c.municipios.pop());
    const resultado = validarPorConsola(carpeta);
    expect(resultado.status).toBe(1);
    expect(resultado.stderr).toContain('municipios.json: /municipios: debe tener al menos 179 elementos');
  });
});
