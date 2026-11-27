// Pure search logic (ARCHITECTURE.md §7.1): no DOM, no clock, no network.
// Rule: unknown data never counts as a match. Promotions that fail no known criterion but
// cannot be confirmed are reported apart ("sin_dato") so the page can say how many it hides.
import type { Disponibilidad, EstadoPromocion, IndiceItem, IndiceTipologia, Programa, Regimen } from './contratos';
import { ESTADOS, PROGRAMAS, REGIMENES } from './etiquetas';

type ProgramaConocido = NonNullable<Programa>;

export const ORDENES = {
  novedad: 'Novedad',
  renta: 'Renta más baja',
  cierre: 'Fecha de cierre',
} as const;
export type Orden = keyof typeof ORDENES;

export const FILTROS_GARAJE = {
  si: 'Incluido u opcional',
  incluido: 'Incluido',
  opcional: 'Opcional',
} as const;
export type FiltroGaraje = keyof typeof FILTROS_GARAJE;

export const MAX_DORMITORIOS = 6;
const MAX_RENTA = 10000;

export interface Filtros {
  municipios: string[];
  regimenes: Regimen[];
  programas: ProgramaConocido[];
  estados: EstadoPromocion[];
  rentaMin: number | null;
  rentaMax: number | null;
  /** At least this many bedrooms. */
  dormitorios: number | null;
  garaje: FiltroGaraje | null;
  /** Included or optional. */
  trastero: boolean;
  soloAbiertas: boolean;
  orden: Orden;
}

export const SIN_FILTROS: Filtros = {
  municipios: [],
  regimenes: [],
  programas: [],
  estados: [],
  rentaMin: null,
  rentaMax: null,
  dormitorios: null,
  garaje: null,
  trastero: false,
  soloAbiertas: false,
  orden: 'novedad',
};

/** Number of active criteria (the sort order is not one). */
export function contarFiltros(f: Filtros): number {
  return [
    f.municipios.length > 0,
    f.regimenes.length > 0,
    f.programas.length > 0,
    f.estados.length > 0,
    f.rentaMin !== null || f.rentaMax !== null,
    f.dormitorios !== null,
    f.garaje !== null,
    f.trastero,
    f.soloAbiertas,
  ].filter(Boolean).length;
}

// ---------------------------------------------------------------- matching

export type Coincidencia = 'si' | 'no' | 'sin_dato';

function todas(resultados: Coincidencia[]): Coincidencia {
  if (resultados.includes('no')) return 'no';
  return resultados.includes('sin_dato') ? 'sin_dato' : 'si';
}

function alguna(resultados: Coincidencia[]): Coincidencia {
  if (resultados.includes('si')) return 'si';
  return resultados.includes('sin_dato') ? 'sin_dato' : 'no';
}

const siNo = (cumple: boolean): Coincidencia => (cumple ? 'si' : 'no');

/** OR within a selection. Selecting the "unknown" value itself (e.g. DESCONOCIDO) is a match. */
function enSeleccion<T>(valor: T, desconocido: boolean, seleccion: readonly T[]): Coincidencia {
  if (seleccion.length === 0 || seleccion.includes(valor)) return 'si';
  return desconocido ? 'sin_dato' : 'no';
}

function porAnejo(valor: Disponibilidad, buscado: FiltroGaraje | null): Coincidencia {
  if (buscado === null) return 'si';
  if (valor === 'desconocido') return 'sin_dato';
  return siNo(buscado === 'si' ? valor === 'incluido' || valor === 'opcional' : valor === buscado);
}

function porDormitorios(valor: number | null, minimo: number | null): Coincidencia {
  if (minimo === null) return 'si';
  return valor === null ? 'sin_dato' : siNo(valor >= minimo);
}

function porRenta(valor: number | null, minimo: number | null, maximo: number | null): Coincidencia {
  if (minimo === null && maximo === null) return 'si';
  if (valor === null) return 'sin_dato';
  return siNo((minimo === null || valor >= minimo) && (maximo === null || valor <= maximo));
}

/** All dwelling criteria must hold for one same dwelling type. */
function porTipologia(t: IndiceTipologia, f: Filtros): Coincidencia {
  return todas([
    porDormitorios(t.dormitorios, f.dormitorios),
    porRenta(t.renta_mensual_eur, f.rentaMin, f.rentaMax),
    porAnejo(t.garaje, f.garaje),
    porAnejo(t.trastero, f.trastero ? 'si' : null),
  ]);
}

function filtraTipologias(f: Filtros): boolean {
  return f.dormitorios !== null || f.rentaMin !== null || f.rentaMax !== null || f.garaje !== null || f.trastero;
}

export function evaluar(p: IndiceItem, f: Filtros): Coincidencia {
  let abierta: Coincidencia = 'si';
  if (f.soloAbiertas && p.estado !== 'inscripcion_abierta') {
    abierta = p.estado === 'desconocido' ? 'sin_dato' : 'no';
  }

  let tipologias: Coincidencia = 'si';
  if (filtraTipologias(f)) {
    tipologias = p.tipologias.length ? alguna(p.tipologias.map((t) => porTipologia(t, f))) : 'sin_dato';
  }

  let programa: Coincidencia = 'si';
  if (f.programas.length) {
    programa = p.programa === null ? 'sin_dato' : siNo(f.programas.includes(p.programa));
  }

  return todas([
    siNo(f.municipios.length === 0 || f.municipios.includes(p.municipio_ine)),
    enSeleccion(p.regimen, p.regimen === 'DESCONOCIDO', f.regimenes),
    programa,
    enSeleccion(p.estado, p.estado === 'desconocido', f.estados),
    abierta,
    tipologias,
  ]);
}

// ---------------------------------------------------------------- sorting

/** Cheapest known rent among the dwelling types that satisfy the filters. */
export function rentaDesde(p: IndiceItem, f: Filtros = SIN_FILTROS): number | null {
  const rentas = p.tipologias
    .filter((t) => porTipologia(t, f) === 'si')
    .flatMap((t) => (t.renta_mensual_eur === null ? [] : [t.renta_mensual_eur]));
  return rentas.length ? Math.min(...rentas) : null;
}

const alfabetico = new Intl.Collator('es', { numeric: true, sensitivity: 'base' });
const porNombre = (a: IndiceItem, b: IndiceItem): number =>
  alfabetico.compare(a.nombre, b.nombre) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);

/** Nulls always go last. */
function conNulosAlFinal<T>(a: T | null, b: T | null, comparar: (a: T, b: T) => number): number {
  if (a === null) return b === null ? 0 : 1;
  return b === null ? -1 : comparar(a, b);
}

const texto = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

/** Deadlines still ahead (nearest first), then past ones (latest first), then unknown. */
function porCierre(a: string | null, b: string | null, hoy: string): number {
  return conNulosAlFinal(a, b, (x, y) => {
    const pasadoX = x < hoy;
    if (pasadoX !== y < hoy) return pasadoX ? 1 : -1;
    return pasadoX ? texto(y, x) : texto(x, y);
  });
}

export function ordenar(items: IndiceItem[], f: Filtros, hoy: string): IndiceItem[] {
  const comparadores: Record<Orden, (a: IndiceItem, b: IndiceItem) => number> = {
    novedad: (a, b) => texto(b.primera_deteccion, a.primera_deteccion),
    renta: (a, b) => conNulosAlFinal(rentaDesde(a, f), rentaDesde(b, f), (x, y) => x - y),
    cierre: (a, b) => porCierre(a.inscripcion_fin, b.inscripcion_fin, hoy),
  };
  return [...items].sort((a, b) => comparadores[f.orden](a, b) || porNombre(a, b));
}

export interface Resultado {
  visibles: IndiceItem[];
  /** Hidden only because some data needed to decide is missing. */
  sinDato: number;
}

/** `hoy` (YYYY-MM-DD) only matters when sorting by closing date. */
export function aplicarFiltros(items: IndiceItem[], f: Filtros, hoy: string): Resultado {
  const visibles: IndiceItem[] = [];
  let sinDato = 0;
  for (const item of items) {
    const coincidencia = evaluar(item, f);
    if (coincidencia === 'si') visibles.push(item);
    else if (coincidencia === 'sin_dato') sinDato += 1;
  }
  return { visibles: ordenar(visibles, f, hoy), sinDato };
}

// ---------------------------------------------------------------- options offered

export interface Opciones {
  municipios: { ine: string; nombre: string }[];
  regimenes: Regimen[];
  programas: ProgramaConocido[];
  estados: EstadoPromocion[];
  /** null when there is no range to choose from. */
  renta: { min: number; max: number } | null;
  dormitorios: number[];
  garaje: boolean;
  trastero: boolean;
}

/** Only values present in the data are offered, in the order of the label tables. */
export function opcionesDisponibles(items: IndiceItem[]): Opciones {
  const municipios = new Map(items.map((p) => [p.municipio_ine, p.municipio]));
  const tipologias = items.flatMap((p) => p.tipologias);
  const rentas = tipologias.flatMap((t) => (t.renta_mensual_eur === null ? [] : [t.renta_mensual_eur]));
  const min = rentas.length ? Math.floor(Math.min(...rentas) / 10) * 10 : 0;
  const max = rentas.length ? Math.ceil(Math.max(...rentas) / 10) * 10 : 0;
  const presentes = <T extends string>(etiquetas: Record<T, string>, valores: (string | null)[]): T[] =>
    (Object.keys(etiquetas) as T[]).filter((clave) => valores.includes(clave));
  const dormitorios = tipologias.flatMap((t) => (t.dormitorios ? [t.dormitorios] : []));
  const mayor = dormitorios.length ? Math.min(MAX_DORMITORIOS, Math.max(...dormitorios)) : 0;

  return {
    municipios: [...municipios]
      .map(([ine, nombre]) => ({ ine, nombre }))
      .sort((a, b) => alfabetico.compare(a.nombre, b.nombre)),
    regimenes: presentes(REGIMENES, items.map((p) => p.regimen)),
    programas: presentes(PROGRAMAS, items.map((p) => p.programa)),
    estados: presentes(ESTADOS, items.map((p) => p.estado)),
    renta: max > min ? { min, max } : null,
    dormitorios: Array.from({ length: mayor }, (_, i) => i + 1),
    garaje: tipologias.some((t) => t.garaje !== 'desconocido'),
    trastero: tipologias.some((t) => t.trastero !== 'desconocido'),
  };
}

// ---------------------------------------------------------------- URL

const unicos = <T>(valores: T[]): T[] => [...new Set(valores)];

/** Accepts both `?mun=a&mun=b` and `?mun=a,b`. */
function lista(params: URLSearchParams, clave: string): string[] {
  return unicos(params.getAll(clave).flatMap((v) => v.split(',')));
}

function entero(valor: string | null, min: number, max: number): number | null {
  if (valor === null || !/^\d{1,5}$/.test(valor)) return null;
  const n = Number(valor);
  return n >= min && n <= max ? n : null;
}

function esClave<T extends string>(tabla: Record<T, unknown>, valor: string | null): valor is T {
  return valor !== null && Object.hasOwn(tabla, valor);
}

/** Query string → filters. Anything invalid is ignored. */
export function leerFiltros(consulta: string): Filtros {
  const params = new URLSearchParams(consulta);
  let rentaMin = entero(params.get('renta_min'), 0, MAX_RENTA);
  let rentaMax = entero(params.get('renta_max'), 0, MAX_RENTA);
  if (rentaMin !== null && rentaMax !== null && rentaMin > rentaMax) {
    rentaMin = null;
    rentaMax = null;
  }
  const garaje = params.get('garaje');
  const orden = params.get('orden');
  return {
    municipios: lista(params, 'mun').filter((v) => /^28\d{3}$/.test(v)),
    regimenes: lista(params, 'reg').filter((v) => esClave(REGIMENES, v)),
    programas: lista(params, 'prog').filter((v) => esClave(PROGRAMAS, v)),
    estados: lista(params, 'estado').filter((v) => esClave(ESTADOS, v)),
    rentaMin,
    rentaMax,
    dormitorios: entero(params.get('dorm'), 1, MAX_DORMITORIOS),
    garaje: esClave(FILTROS_GARAJE, garaje) ? garaje : null,
    trastero: params.get('trastero') === '1',
    soloAbiertas: params.get('abierta') === '1',
    orden: esClave(ORDENES, orden) ? orden : SIN_FILTROS.orden,
  };
}

/** Filters → query string without "?". Defaults are omitted, so no filters gives "". */
export function escribirFiltros(f: Filtros): string {
  const params = new URLSearchParams();
  for (const v of f.municipios) params.append('mun', v);
  for (const v of f.regimenes) params.append('reg', v);
  for (const v of f.programas) params.append('prog', v);
  for (const v of f.estados) params.append('estado', v);
  if (f.rentaMin !== null) params.set('renta_min', String(f.rentaMin));
  if (f.rentaMax !== null) params.set('renta_max', String(f.rentaMax));
  if (f.dormitorios !== null) params.set('dorm', String(f.dormitorios));
  if (f.garaje !== null) params.set('garaje', f.garaje);
  if (f.trastero) params.set('trastero', '1');
  if (f.soloAbiertas) params.set('abierta', '1');
  if (f.orden !== SIN_FILTROS.orden) params.set('orden', f.orden);
  return params.toString();
}
