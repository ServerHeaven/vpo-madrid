import { describe, expect, it } from 'vitest';
import {
  FUERA_DE_LA_COMUNIDAD,
  type EntradaCalculadora,
  type EstadoRegla,
  type IdRegla,
  type IpremAnual,
  type Parametro,
  type PromocionCalculadora,
  type RequisitosCalculadora,
  type ResultadoPromocion,
} from '../src/lib/contratos-calculadora';
import { estimarBaseImponible, evaluarPromocion, evaluarTodas, ipremAplicable } from '../src/lib/eligibility';
import { formatEur } from '../src/lib/format';
import type { Origen } from '../src/lib/requisitos';
import type { IngresosPorMiembros } from '../src/lib/types';

// ---------------------------------------------------------------- builders

const p = <T>(valor: T, origen: Origen = 'convocatoria', sin_verificar = false): Parametro<T> => ({
  valor,
  origen,
  sin_verificar,
});
const desconocido = <T>(): Parametro<T> => ({ valor: null, origen: 'desconocido', sin_verificar: false });
const noExigido = <T>(): Parametro<T> => ({ valor: null, origen: 'no_exigido', sin_verificar: false });

// Synthetic figures: 2026 differs on purpose so the tests can tell the years apart.
const IPREM: IpremAnual[] = [
  { anio: 2024, anual_12: 7200, anual_14: 8400, verificado: true },
  { anio: 2026, anual_12: 7500, anual_14: 8750, verificado: true },
  { anio: 2025, anual_12: 7200, anual_14: 8400, verificado: true },
];

type Padron = NonNullable<RequisitosCalculadora['empadronamiento']['valor']>;
type Edad = NonNullable<RequisitosCalculadora['edad']['valor']>;

const padron = (cambios: Partial<Padron> = {}): Padron => ({
  ambito: 'municipio',
  municipio_ine: '28079',
  anios_min: 3,
  ininterrumpido: null,
  alternativa_trabajo: false,
  ...cambios,
});
const edad = (min: number | null, max: number | null, tipo: Edad['tipo'] = 'requisito'): Edad => ({
  min,
  max,
  tipo,
});

/** Requirements that the base entry below satisfies in full. */
function requisitos(cambios: Partial<RequisitosCalculadora> = {}): RequisitosCalculadora {
  return {
    ingresos_min_iprem: p(1),
    ingresos_max_iprem: p(5.5),
    ingresos_por_miembros: null,
    iprem_pagas: p<14>(14),
    iprem_ejercicio: desconocido(),
    tasa_esfuerzo_max: p(0.35),
    empadronamiento: p(padron()),
    edad: p(edad(18, 65)),
    no_titular_vivienda: p(true),
    // Stands for a convocatoria that does not weigh the income, so no warning is due.
    coeficientes_ponderacion: noExigido(),
    condiciones: [],
    ...cambios,
  };
}

function promo(
  reqs: Partial<RequisitosCalculadora> = {},
  resto: Partial<Omit<PromocionCalculadora, 'requisitos'>> = {},
): PromocionCalculadora {
  return {
    id: 'p',
    nombre: 'Prueba',
    operador: 'Operador',
    municipio_ine: '28079',
    municipio: 'Madrid',
    estado: 'inscripcion_abierta',
    activa_en_fuente: true,
    tipologias: [{ dormitorios: 2, renta_mensual_eur: 600 }],
    requisitos: requisitos(reqs),
    ...resto,
  };
}

function entrada(cambios: Partial<EntradaCalculadora> = {}): EntradaCalculadora {
  return {
    ingresos_anuales: 30000,
    ingresos_estimados: false,
    ejercicio: 2025,
    miembros: 2,
    municipio_empadronamiento: '28079',
    anios_empadronamiento: 5,
    municipio_trabajo: null,
    anios_trabajo: null,
    edad: 30,
    titular_vivienda: false,
    dormitorios_min: null,
    ...cambios,
  };
}

const evaluar = (
  reqs: Partial<RequisitosCalculadora> = {},
  datos: Partial<EntradaCalculadora> = {},
  resto: Partial<Omit<PromocionCalculadora, 'requisitos'>> = {},
  tabla: IpremAnual[] = IPREM,
): ResultadoPromocion => evaluarPromocion(promo(reqs, resto), entrada(datos), tabla);

function regla(r: ResultadoPromocion, id: IdRegla) {
  const encontrada = r.reglas.find((x) => x.id === id);
  if (!encontrada) throw new Error(`Falta la regla ${id}`);
  return encontrada;
}

const fila = (
  miembros_desde: number,
  miembros_hasta: number | null,
  min_iprem: number | null,
  max_iprem: number | null,
): IngresosPorMiembros => ({ miembros_desde, miembros_hasta, min_iprem, max_iprem });

const conTabla = (filas: IngresosPorMiembros[]): Partial<RequisitosCalculadora> => ({
  ingresos_min_iprem: null,
  ingresos_max_iprem: null,
  ingresos_por_miembros: p(filas),
});

const IDS: IdRegla[] = [
  'ingresos_max',
  'ingresos_min',
  'tasa_esfuerzo',
  'empadronamiento',
  'edad',
  'titularidad',
  'estado',
];

// ---------------------------------------------------------------- helpers

describe('estimarBaseImponible', () => {
  it.each([
    [30000, 26095],
    [20000, 16730],
    [12345.67, 9561.72],
    [2135.51, 0], // 1999.905… after social security: below the 2 000 € of expenses
    [0, 0],
    [-100, 0],
  ])('bruto %s → %s', (bruto, base) => {
    expect(estimarBaseImponible(bruto)).toBe(base);
  });
});

describe('ipremAplicable', () => {
  it.each([
    [2025, 14, { importe: 8400, anio: 2025, pagas: 14, sustituido: false }],
    [2025, 12, { importe: 7200, anio: 2025, pagas: 12, sustituido: false }],
    [2026, 14, { importe: 8750, anio: 2026, pagas: 14, sustituido: false }],
    [2027, 14, { importe: 8750, anio: 2026, pagas: 14, sustituido: true }],
    [2010, 12, { importe: 7500, anio: 2026, pagas: 12, sustituido: true }],
  ] as const)('ejercicio %s, %s pagas', (ejercicio, pagas, esperado) => {
    expect(ipremAplicable(IPREM, ejercicio, pagas)).toEqual(esperado);
  });

  it('con la tabla vacía no inventa un importe', () => {
    expect(() => ipremAplicable([], 2025, 14)).toThrow();
  });
});

// ---------------------------------------------------------------- base case

describe('caso base', () => {
  it('cumple todo: elegible, sin avisos, con las siete reglas en orden', () => {
    const r = evaluar();
    expect(r.veredicto).toBe('elegible');
    expect(r.motivo_no_elegible).toBeNull();
    expect(r.avisos).toEqual([]);
    expect(r.reglas.map((x) => x.id)).toEqual(IDS);
    expect(r.reglas.map((x) => x.estado)).toEqual([
      'CUMPLE',
      'CUMPLE',
      'CUMPLE',
      'CUMPLE',
      'CUMPLE',
      'CUMPLE',
      'INFORMATIVO',
    ]);
    for (const x of r.reglas) expect(x.explicacion.length).toBeGreaterThan(0);
    expect(regla(r, 'estado').origen).toBeNull();
    expect(regla(r, 'edad').origen).toBe('convocatoria');
  });

  it('devuelve la promoción recibida', () => {
    const promocion = promo();
    expect(evaluarPromocion(promocion, entrada(), IPREM).promocion).toBe(promocion);
  });

  it('no modifica sus argumentos', () => {
    const promocion = promo();
    const datos = entrada();
    const copia = JSON.stringify([promocion, datos, IPREM]);
    evaluarTodas([promocion], datos, IPREM, { mostrarFinalizadas: false });
    expect(JSON.stringify([promocion, datos, IPREM])).toBe(copia);
  });

  it('los ingresos estimados no cambian las reglas', () => {
    expect(evaluar({}, { ingresos_estimados: true }).reglas).toEqual(evaluar().reglas);
  });
});

// ---------------------------------------------------------------- R1 and R2

describe('R1 y R2: fronteras exactas', () => {
  it.each([
    // veces, lado, ingresos, esperado (IPREM 2025, 14 pagas = 8400)
    [5.5, 'max', 46200, 'CUMPLE'],
    [5.5, 'max', 46200.01, 'NO_CUMPLE'],
    [5.5, 'max', 46199.99, 'CUMPLE'],
    [7.5, 'max', 63000, 'CUMPLE'],
    [7.5, 'max', 63000.01, 'NO_CUMPLE'],
    [7.5, 'max', 62999.99, 'CUMPLE'],
    [1.1, 'max', 9240, 'CUMPLE'], // 1.1 × 8400 is not exact in floating point
    [1.1, 'max', 9240.01, 'NO_CUMPLE'],
    [1.5, 'min', 12600, 'CUMPLE'],
    [1.5, 'min', 12599.99, 'NO_CUMPLE'],
    [1.5, 'min', 12600.01, 'CUMPLE'],
    [1.1, 'min', 9240, 'CUMPLE'],
    [1.1, 'min', 9239.99, 'NO_CUMPLE'],
    [5.5, 'min', 46200, 'CUMPLE'],
    [0, 'min', 0, 'CUMPLE'],
    [5.5, 'max', 0, 'CUMPLE'],
    [1, 'min', 0, 'NO_CUMPLE'],
  ] as const)('%s IPREM (%s) con %s € → %s', (veces, lado, ingresos, esperado) => {
    const clave = lado === 'max' ? 'ingresos_max_iprem' : 'ingresos_min_iprem';
    const r = evaluar({ [clave]: p(veces) }, { ingresos_anuales: ingresos });
    expect(regla(r, lado === 'max' ? 'ingresos_max' : 'ingresos_min').estado).toBe(esperado);
  });

  it('explica el límite en euros', () => {
    const r = evaluar({}, { ingresos_anuales: 46200.01 });
    expect(regla(r, 'ingresos_max').explicacion).toContain(formatEur(46200.01));
    expect(regla(r, 'ingresos_max').explicacion).toContain(formatEur(46200));
    expect(r.veredicto).toBe('no_elegible');
    expect(r.motivo_no_elegible).toBe(regla(r, 'ingresos_max').explicacion);
  });

  it.each([
    ['ingresos_max_iprem', 'ingresos_max'],
    ['ingresos_min_iprem', 'ingresos_min'],
  ] as const)('%s: desconocido, no exigido y ausente', (clave, id) => {
    expect(regla(evaluar({ [clave]: desconocido() }), id)).toMatchObject({
      estado: 'DESCONOCIDO',
      origen: 'desconocido',
    });
    expect(regla(evaluar({ [clave]: noExigido() }), id)).toMatchObject({
      estado: 'CUMPLE',
      origen: 'no_exigido',
    });
    expect(regla(evaluar({ [clave]: null }), id).estado).toBe('DESCONOCIDO');
  });

  it.each([Number.NaN, -1, Number.POSITIVE_INFINITY])('ingresos no válidos (%s): DESCONOCIDO', (ingresos) => {
    const r = evaluar({}, { ingresos_anuales: ingresos });
    for (const id of ['ingresos_max', 'ingresos_min', 'tasa_esfuerzo'] as const) {
      expect(regla(r, id).estado).toBe('DESCONOCIDO');
    }
    expect(r.veredicto).toBe('posiblemente');
  });
});

describe('R1 y R2: tabla por miembros', () => {
  const filas = [fila(1, 1, 1, 3.5), fila(2, 3, 1.5, 4.5), fila(4, null, 2, 5.5)];

  it.each([
    [1, 29400, 'CUMPLE'],
    [1, 29400.01, 'NO_CUMPLE'],
    [2, 37800, 'CUMPLE'],
    [3, 37800, 'CUMPLE'],
    [3, 37800.01, 'NO_CUMPLE'],
    [4, 46200, 'CUMPLE'],
    [10, 46200, 'CUMPLE'],
    [10, 46200.01, 'NO_CUMPLE'],
  ] as const)('%s miembros con %s € → máximo %s', (miembros, ingresos, esperado) => {
    const r = evaluar(conTabla(filas), { miembros, ingresos_anuales: ingresos });
    expect(regla(r, 'ingresos_max')).toMatchObject({ estado: esperado, origen: 'convocatoria' });
  });

  it.each([
    [2, 12600, 'CUMPLE'],
    [2, 12599.99, 'NO_CUMPLE'],
    [4, 16800, 'CUMPLE'],
    [4, 16799.99, 'NO_CUMPLE'],
  ] as const)('%s miembros con %s € → mínimo %s', (miembros, ingresos, esperado) => {
    const r = evaluar(conTabla(filas), { miembros, ingresos_anuales: ingresos });
    expect(regla(r, 'ingresos_min').estado).toBe(esperado);
  });

  it('la tabla prevalece sobre los límites generales', () => {
    const r = evaluar(
      { ingresos_max_iprem: p(7.5), ingresos_por_miembros: p([fila(1, null, 1, 3)]) },
      { ingresos_anuales: 30000 },
    );
    expect(regla(r, 'ingresos_max').estado).toBe('NO_CUMPLE');
  });

  it.each([
    ['sin fila para el tamaño', [fila(3, null, 1, 5)], 'DESCONOCIDO', 'DESCONOCIDO'],
    ['tabla vacía', [], 'DESCONOCIDO', 'DESCONOCIDO'],
    ['mínimo nulo en la fila', [fila(1, null, null, 5.5)], 'CUMPLE', 'DESCONOCIDO'],
    ['máximo nulo en la fila', [fila(1, null, 1, null)], 'DESCONOCIDO', 'CUMPLE'],
    ['fila entera nula', [fila(1, null, null, null)], 'DESCONOCIDO', 'DESCONOCIDO'],
    ['filas solapadas que discrepan', [fila(1, 2, 1, 5.5), fila(2, null, 1, 4)], 'DESCONOCIDO', 'CUMPLE'],
  ] as const)('%s', (_caso, filasCaso, max, min) => {
    const r = evaluar(conTabla([...filasCaso]));
    expect(regla(r, 'ingresos_max').estado).toBe(max);
    expect(regla(r, 'ingresos_min').estado).toBe(min);
  });

  it('un parámetro de tabla sin valor: desconocido o no exigido según el origen', () => {
    const vacia = (parametro: Parametro<IngresosPorMiembros[]>) =>
      evaluar({ ingresos_min_iprem: null, ingresos_max_iprem: null, ingresos_por_miembros: parametro });
    expect(regla(vacia(desconocido()), 'ingresos_max').estado).toBe('DESCONOCIDO');
    expect(regla(vacia(noExigido()), 'ingresos_max').estado).toBe('CUMPLE');
  });
});

// ---------------------------------------------------------------- IPREM

describe('IPREM: año, pagas y avisos', () => {
  it('las bases fijan el año y prevalecen, con aviso si difiere', () => {
    // 5.5 × 8750 (2026) = 48125
    const r = evaluar({ iprem_ejercicio: p(2026) }, { ingresos_anuales: 48125, ejercicio: 2025 });
    expect(regla(r, 'ingresos_max').estado).toBe('CUMPLE');
    expect(r.avisos).toHaveLength(1);
    expect(r.avisos[0]).toMatch(/2026.*2025/);
  });

  it('sin aviso si las bases fijan el mismo año', () => {
    expect(evaluar({ iprem_ejercicio: p(2025) }).avisos).toEqual([]);
  });

  it.each([null, 2030])('año ausente de la tabla (bases: %s): usa el último y avisa', (bases) => {
    const r = evaluar(
      { iprem_ejercicio: bases === null ? desconocido() : p(bases) },
      { ejercicio: bases ?? 2030, ingresos_anuales: 48125 },
    );
    expect(regla(r, 'ingresos_max').estado).toBe('CUMPLE');
    expect(r.avisos).toHaveLength(1);
    expect(r.avisos[0]).toMatch(/2030.*2026/);
    expect(r.veredicto).not.toBe('no_elegible');
  });

  it('12 pagas', () => {
    // 5.5 × 7200 = 39600
    const r = evaluar({ iprem_pagas: p<12>(12) }, { ingresos_anuales: 39600.01 });
    expect(regla(r, 'ingresos_max').estado).toBe('NO_CUMPLE');
    expect(r.avisos).toEqual([]);
  });

  it('pagas desconocidas: asume 14 y avisa', () => {
    const r = evaluar({ iprem_pagas: desconocido() }, { ingresos_anuales: 46200 });
    expect(regla(r, 'ingresos_max').estado).toBe('CUMPLE');
    expect(r.avisos).toHaveLength(1);
    expect(r.avisos[0]).toContain('14 pagas');
    expect(r.veredicto).toBe('elegible'); // an assumed default, not an unknown rule
  });

  it('sin límites que evaluar no hay avisos del IPREM', () => {
    const r = evaluar(
      {
        ingresos_min_iprem: noExigido(),
        ingresos_max_iprem: desconocido(),
        iprem_pagas: desconocido(),
        iprem_ejercicio: p(2030),
      },
      { ejercicio: 2025 },
    );
    expect(r.avisos).toEqual([]);
  });

  it('IPREM sin verificar: avisa sin cambiar el veredicto', () => {
    const r = evaluar({}, {}, {}, [{ anio: 2025, anual_12: 7200, anual_14: 8400, verificado: false }]);
    expect(r.veredicto).toBe('elegible');
    expect(r.avisos).toHaveLength(1);
  });

  it('tabla del IPREM vacía: ingresos DESCONOCIDO y aviso', () => {
    const r = evaluar({}, {}, {}, []);
    expect(regla(r, 'ingresos_max').estado).toBe('DESCONOCIDO');
    expect(regla(r, 'ingresos_min').estado).toBe('DESCONOCIDO');
    expect(r.avisos).toHaveLength(1);
  });
});

describe('coeficientes de ponderación', () => {
  it('si no constan, compara sin ponderar y lo avisa', () => {
    const r = evaluar({ coeficientes_ponderacion: desconocido() });
    expect(r.avisos).toHaveLength(1);
    expect(r.avisos[0]).toContain('sin ponderar');
  });

  const coef = p({ '1': 1, '2': 0.9, '3': 0.8 }, 'programa');

  it.each([
    [2, 51333.33, 'CUMPLE'], // × 0.9 = 46199.997
    [2, 51333.34, 'NO_CUMPLE'], // × 0.9 = 46200.006
    [3, 57750, 'CUMPLE'], // × 0.8 = 46200 exactly
    [3, 57750.01, 'NO_CUMPLE'],
    [1, 46200.01, 'NO_CUMPLE'],
  ] as const)('%s miembros con %s € → %s', (miembros, ingresos, esperado) => {
    const r = evaluar({ coeficientes_ponderacion: coef }, { miembros, ingresos_anuales: ingresos });
    expect(regla(r, 'ingresos_max').estado).toBe(esperado);
  });

  it('el mínimo también usa los ingresos ponderados', () => {
    const r = evaluar({ coeficientes_ponderacion: coef }, { ingresos_anuales: 9000 }); // × 0.9 = 8100
    expect(regla(r, 'ingresos_min').estado).toBe('NO_CUMPLE');
  });

  it('la tasa de esfuerzo usa los ingresos sin ponderar', () => {
    // 600 × 12 / 0.35 = 20571.43; weighted 21000 × 0.9 = 18900 would fail
    const r = evaluar({ coeficientes_ponderacion: coef }, { ingresos_anuales: 21000 });
    expect(regla(r, 'tasa_esfuerzo').estado).toBe('CUMPLE');
  });

  it('falta el tamaño del hogar: ingresos DESCONOCIDO', () => {
    const r = evaluar({ coeficientes_ponderacion: coef }, { miembros: 5 });
    expect(regla(r, 'ingresos_max').estado).toBe('DESCONOCIDO');
    expect(regla(r, 'ingresos_min').estado).toBe('DESCONOCIDO');
    expect(r.avisos).toEqual([]);
  });

  it('un requisito no exigido sigue cumplido aunque falte el coeficiente', () => {
    const r = evaluar({ coeficientes_ponderacion: coef, ingresos_min_iprem: noExigido() }, { miembros: 5 });
    expect(regla(r, 'ingresos_min').estado).toBe('CUMPLE');
  });
});

describe('valores generales sin verificar', () => {
  it.each([
    ['ingresos_max_iprem', p(5.5, 'regimen', true), 'ingresos_max'],
    ['ingresos_min_iprem', p(1, 'programa', true), 'ingresos_min'],
    ['tasa_esfuerzo_max', p(0.35, 'programa', true), 'tasa_esfuerzo'],
    ['empadronamiento', p(padron(), 'programa', true), 'empadronamiento'],
    ['edad', p(edad(18, 65), 'regimen', true), 'edad'],
    ['edad', p(edad(null, 35, 'cupo'), 'regimen', true), 'edad'],
    ['no_titular_vivienda', p(true, 'regimen', true), 'titularidad'],
    ['iprem_pagas', p<14>(14, 'regimen', true), 'ingresos_max'],
    ['coeficientes_ponderacion', p({ '2': 1 }, 'programa', true), 'ingresos_max'],
  ] as const)('%s → posiblemente', (clave, parametro, id) => {
    const r = evaluar({ [clave]: parametro });
    expect(regla(r, id).sin_verificar).toBe(true);
    expect(r.veredicto).toBe('posiblemente');
    expect(r.motivo_no_elegible).toBeNull();
  });

  it('un valor general verificado permite ser elegible', () => {
    const r = evaluar({ ingresos_max_iprem: p(5.5, 'regimen') });
    expect(r.veredicto).toBe('elegible');
    expect(regla(r, 'ingresos_max').origen).toBe('regimen');
  });

  it('un NO_CUMPLE manda sobre lo no verificado', () => {
    const r = evaluar({ ingresos_max_iprem: p(1, 'regimen', true) });
    expect(r.veredicto).toBe('no_elegible');
  });
});

// ---------------------------------------------------------------- R3

describe('R3: tasa de esfuerzo', () => {
  const tipos = (...rentas: (number | null)[]) => ({
    tipologias: rentas.map((renta_mensual_eur, i) => ({ dormitorios: i + 1, renta_mensual_eur })),
  });

  it.each([
    // tasa, renta, ingresos, esperado
    [0.35, 700, 24000, 'CUMPLE'],
    [0.35, 700, 23999.99, 'NO_CUMPLE'],
    [0.3, 500, 20000, 'CUMPLE'],
    [0.3, 500, 19999.99, 'NO_CUMPLE'],
    [0.35, 350, 12000, 'CUMPLE'],
    [0.35, 700.01, 24000, 'NO_CUMPLE'],
    [1, 1000, 12000, 'CUMPLE'],
    [0.35, 700, 0, 'NO_CUMPLE'],
  ] as const)('tasa %s, renta %s, ingresos %s → %s', (tasa, renta, ingresos, esperado) => {
    const r = evaluar({ tasa_esfuerzo_max: p(tasa) }, { ingresos_anuales: ingresos }, tipos(renta));
    expect(r.tipologias[0]!.estado).toBe(esperado);
    expect(regla(r, 'tasa_esfuerzo').estado).toBe(esperado);
  });

  it.each([
    ['una cumple y otra no', [600, 2000], 'CUMPLE'],
    ['una cumple y otra sin renta', [null, 600], 'CUMPLE'],
    ['todas fallan', [2000, 3000], 'NO_CUMPLE'],
    ['falla una y otra sin renta', [2000, null], 'DESCONOCIDO'],
    ['ninguna renta', [null, null], 'DESCONOCIDO'],
    ['sin tipologías', [], 'DESCONOCIDO'],
  ] as const)('%s → %s', (_caso, rentas, esperado) => {
    const r = evaluar({}, {}, tipos(...rentas));
    expect(regla(r, 'tasa_esfuerzo').estado).toBe(esperado);
  });

  it('detalla cada tipología con su ingreso mínimo', () => {
    const r = evaluar({}, { ingresos_anuales: 24000 }, tipos(700, 900, null));
    expect(r.tipologias).toEqual([
      { dormitorios: 1, renta_mensual_eur: 700, estado: 'CUMPLE', ingreso_minimo_anual: 24000 },
      {
        dormitorios: 2,
        renta_mensual_eur: 900,
        estado: 'NO_CUMPLE',
        ingreso_minimo_anual: expect.closeTo(30857.142857, 4),
      },
      { dormitorios: 3, renta_mensual_eur: null, estado: 'DESCONOCIDO', ingreso_minimo_anual: null },
    ]);
    expect(regla(r, 'tasa_esfuerzo').explicacion).toContain(formatEur(24000));
    expect(regla(r, 'tasa_esfuerzo').explicacion).toContain('1 dormitorio');
  });

  it('al fallar todas dice cuánto hace falta para la más barata', () => {
    const r = evaluar({}, { ingresos_anuales: 0 }, tipos(900, 700));
    expect(regla(r, 'tasa_esfuerzo').estado).toBe('NO_CUMPLE');
    expect(regla(r, 'tasa_esfuerzo').explicacion).toContain(formatEur(24000));
    expect(r.tipologias.map((t) => t.ingreso_minimo_anual)).toEqual([expect.closeTo(30857.142857, 4), 24000]);
  });

  it('tasa desconocida: todo DESCONOCIDO y sin ingreso mínimo', () => {
    const r = evaluar({ tasa_esfuerzo_max: desconocido() }, {}, tipos(700, null));
    expect(regla(r, 'tasa_esfuerzo').estado).toBe('DESCONOCIDO');
    expect(r.tipologias.map((t) => [t.estado, t.ingreso_minimo_anual])).toEqual([
      ['DESCONOCIDO', null],
      ['DESCONOCIDO', null],
    ]);
  });

  it.each([[[700, null]], [[]]])('tasa no exigida (rentas %j): CUMPLE', (rentas) => {
    const r = evaluar({ tasa_esfuerzo_max: noExigido() }, { ingresos_anuales: 0 }, tipos(...rentas));
    expect(regla(r, 'tasa_esfuerzo').estado).toBe('CUMPLE');
    expect(r.tipologias.every((t) => t.estado === 'CUMPLE' && t.ingreso_minimo_anual === null)).toBe(true);
  });

  it.each([0, -0.1, Number.NaN])('tasa fuera de rango (%s): DESCONOCIDO', (tasa) => {
    expect(regla(evaluar({ tasa_esfuerzo_max: p(tasa) }), 'tasa_esfuerzo').estado).toBe('DESCONOCIDO');
  });
});

// ---------------------------------------------------------------- R4

describe('R4: empadronamiento', () => {
  type Casa = [string | null, number | null];
  const NADA: Casa = [null, null];

  const caso = (valor: Padron, casa: Casa, trabajo: Casa = NADA) =>
    regla(
      evaluar(
        { empadronamiento: p(valor) },
        {
          municipio_empadronamiento: casa[0],
          anios_empadronamiento: casa[1],
          municipio_trabajo: trabajo[0],
          anios_trabajo: trabajo[1],
        },
      ),
      'empadronamiento',
    ).estado;

  const municipio = padron({ anios_min: 3 });
  const comunidad = padron({ ambito: 'comunidad', municipio_ine: null, anios_min: 3 });

  it.each([
    ['municipio, años exactos', municipio, ['28079', 3], 'CUMPLE'],
    ['municipio, un poco menos', municipio, ['28079', 2.99], 'NO_CUMPLE'],
    ['municipio, decimales', padron({ anios_min: 2.5 }), ['28079', 2.5], 'CUMPLE'],
    ['municipio, decimales por debajo', padron({ anios_min: 2.5 }), ['28079', 2.4], 'NO_CUMPLE'],
    ['municipio, otro municipio', municipio, ['28005', 10], 'NO_CUMPLE'],
    ['municipio, otro municipio sin años', municipio, ['28005', null], 'NO_CUMPLE'],
    ['municipio, fuera', municipio, [FUERA_DE_LA_COMUNIDAD, 10], 'NO_CUMPLE'],
    ['municipio, sin municipio', municipio, [null, 10], 'DESCONOCIDO'],
    ['municipio, sin años', municipio, ['28079', null], 'DESCONOCIDO'],
    ['municipio, sin nada', municipio, [null, null], 'DESCONOCIDO'],
    ['municipio, años negativos', municipio, ['28079', -1], 'DESCONOCIDO'],
    ['comunidad, cualquier 28xxx', comunidad, ['28005', 3], 'CUMPLE'],
    ['comunidad, pocos años', comunidad, ['28005', 1], 'NO_CUMPLE'],
    ['comunidad, fuera', comunidad, [FUERA_DE_LA_COMUNIDAD, 20], 'NO_CUMPLE'],
    ['comunidad, otro código', comunidad, ['08019', 20], 'NO_CUMPLE'],
    ['comunidad, sin municipio', comunidad, [null, 20], 'DESCONOCIDO'],
    ['comunidad, sin años', comunidad, ['28005', null], 'DESCONOCIDO'],
    ['0 años: basta el lugar', padron({ anios_min: 0 }), ['28079', null], 'CUMPLE'],
    ['0 años, otro lugar', padron({ anios_min: 0 }), ['28005', null], 'NO_CUMPLE'],
    ['0 años, sin lugar', padron({ anios_min: 0 }), [null, null], 'DESCONOCIDO'],
    ['anios_min nulo', padron({ anios_min: null }), ['28079', 10], 'DESCONOCIDO'],
    ['anios_min nulo, fuera', padron({ anios_min: null }), [FUERA_DE_LA_COMUNIDAD, 10], 'DESCONOCIDO'],
    ['comunidad, anios_min nulo', { ...comunidad, anios_min: null }, ['28005', 10], 'DESCONOCIDO'],
    ['municipio sin código', padron({ municipio_ine: null }), ['28079', 10], 'DESCONOCIDO'],
  ] as [string, Padron, Casa, EstadoRegla][])('%s', (_nombre, valor, casa, esperado) => {
    expect(caso(valor, casa)).toBe(esperado);
  });

  const conTrabajo = (alternativa: boolean | null, base: Padron = municipio): Padron => ({
    ...base,
    alternativa_trabajo: alternativa,
  });
  const LEJOS: Casa = ['28005', 10];

  it.each([
    ['vale el trabajo', conTrabajo(true), LEJOS, ['28079', 3], 'CUMPLE'],
    ['vale el trabajo, sin casa', conTrabajo(true), NADA, ['28079', 3], 'CUMPLE'],
    ['trabajo con pocos años', conTrabajo(true), LEJOS, ['28079', 2], 'NO_CUMPLE'],
    ['trabajo en otro sitio', conTrabajo(true), LEJOS, ['28005', 10], 'NO_CUMPLE'],
    ['trabajo fuera', conTrabajo(true), LEJOS, [FUERA_DE_LA_COMUNIDAD, 10], 'NO_CUMPLE'],
    ['trabajo sin indicar', conTrabajo(true), LEJOS, NADA, 'DESCONOCIDO'],
    ['trabajo sin años', conTrabajo(true), LEJOS, ['28079', null], 'DESCONOCIDO'],
    ['casa sin indicar y trabajo no vale', conTrabajo(true), NADA, ['28005', 10], 'DESCONOCIDO'],
    ['casa vale y trabajo sin indicar', conTrabajo(true), ['28079', 5], NADA, 'CUMPLE'],
    ['comunidad, vale el trabajo', conTrabajo(true, comunidad), [FUERA_DE_LA_COMUNIDAD, 10], ['28005', 4], 'CUMPLE'],
    ['comunidad, trabajo fuera', conTrabajo(true, comunidad), [FUERA_DE_LA_COMUNIDAD, 9], ['08019', 9], 'NO_CUMPLE'],
    ['0 años por trabajo', conTrabajo(true, padron({ anios_min: 0 })), LEJOS, ['28079', null], 'CUMPLE'],
    ['trabajo no admitido', conTrabajo(false), LEJOS, ['28079', 10], 'NO_CUMPLE'],
    ['no se sabe y solo valdría el trabajo', conTrabajo(null), LEJOS, ['28079', 10], 'DESCONOCIDO'],
    ['no se sabe y el trabajo podría valer', conTrabajo(null), LEJOS, ['28079', null], 'DESCONOCIDO'],
    ['no se sabe y el trabajo no vale', conTrabajo(null), LEJOS, ['28079', 1], 'NO_CUMPLE'],
    ['no se sabe y no indica trabajo', conTrabajo(null), LEJOS, NADA, 'NO_CUMPLE'],
    ['no se sabe y la casa vale', conTrabajo(null), ['28079', 5], NADA, 'CUMPLE'],
    ['no se sabe, casa sin indicar', conTrabajo(null), NADA, ['28079', 10], 'DESCONOCIDO'],
  ] as [string, Padron, Casa, Casa, EstadoRegla][])('%s', (_nombre, valor, casa, trabajo, esperado) => {
    expect(caso(valor, casa, trabajo)).toBe(esperado);
  });

  it('desconocido y no exigido', () => {
    expect(regla(evaluar({ empadronamiento: desconocido() }), 'empadronamiento').estado).toBe('DESCONOCIDO');
    const r = evaluar({ empadronamiento: noExigido() }, { municipio_empadronamiento: null });
    expect(regla(r, 'empadronamiento')).toMatchObject({ estado: 'CUMPLE', origen: 'no_exigido' });
  });

  it('nombra el municipio de la promoción o su código INE', () => {
    expect(regla(evaluar(), 'empadronamiento').explicacion).toContain('Madrid');
    const otro = evaluar({ empadronamiento: p(padron({ municipio_ine: '28005' })) });
    expect(regla(otro, 'empadronamiento').explicacion).toContain('28005');
  });
});

// ---------------------------------------------------------------- R5

describe('R5: edad', () => {
  const caso = (valor: Edad, anios: number | null) =>
    regla(evaluar({ edad: p(valor) }, { edad: anios }), 'edad');

  it.each([
    [edad(null, 34), 34, 'CUMPLE'], // "menores de 35"
    [edad(null, 34), 35, 'NO_CUMPLE'],
    [edad(18, 65), 18, 'CUMPLE'],
    [edad(18, 65), 65, 'CUMPLE'],
    [edad(18, 65), 17, 'NO_CUMPLE'],
    [edad(18, 65), 66, 'NO_CUMPLE'],
    [edad(65, null), 64, 'NO_CUMPLE'],
    [edad(65, null), 99, 'CUMPLE'],
    [edad(null, null), 30, 'DESCONOCIDO'],
    [edad(null, null), null, 'DESCONOCIDO'],
    [edad(18, 35), null, 'DESCONOCIDO'],
    [edad(18, 35), Number.NaN, 'DESCONOCIDO'],
  ] as const)('requisito %j con %s años → %s', (valor, anios, esperado) => {
    expect(caso(valor, anios).estado).toBe(esperado);
  });

  it.each([
    [edad(null, 35, 'cupo'), 35, /optas al cupo reservado/i],
    [edad(null, 35, 'cupo'), 36, /cupo general/i],
    [edad(65, null, 'cupo'), 65, /optas al cupo reservado/i],
    [edad(65, null, 'cupo'), 64, /cupo general/i],
    [edad(null, 35, 'cupo'), null, /indica tu edad/i],
    [edad(null, null, 'cupo'), 30, /cupo/i],
  ] as const)('cupo %j con %s años es informativo', (valor, anios, texto) => {
    const r = caso(valor, anios);
    expect(r.estado).toBe('INFORMATIVO');
    expect(r.explicacion).toMatch(texto);
  });

  it('desconocido y no exigido', () => {
    expect(regla(evaluar({ edad: desconocido() }), 'edad').estado).toBe('DESCONOCIDO');
    expect(regla(evaluar({ edad: noExigido() }, { edad: null }), 'edad').estado).toBe('CUMPLE');
  });
});

// ---------------------------------------------------------------- R6

describe('R6: titularidad de otra vivienda', () => {
  it.each([
    [p(true), true, 'NO_CUMPLE'],
    [p(true), false, 'CUMPLE'],
    [p(true), null, 'DESCONOCIDO'],
    [p(false), true, 'CUMPLE'],
    [p(false), false, 'CUMPLE'],
    [p(false), null, 'CUMPLE'],
    [desconocido<boolean>(), true, 'DESCONOCIDO'],
    [desconocido<boolean>(), false, 'DESCONOCIDO'],
    [desconocido<boolean>(), null, 'DESCONOCIDO'],
    [noExigido<boolean>(), true, 'CUMPLE'],
    [noExigido<boolean>(), null, 'CUMPLE'],
  ] as const)('exigencia %j, titular %s → %s', (parametro, titular, esperado) => {
    const r = evaluar({ no_titular_vivienda: parametro }, { titular_vivienda: titular });
    expect(regla(r, 'titularidad').estado).toBe(esperado);
  });

  it('recuerda las excepciones de las bases', () => {
    const r = evaluar({}, { titular_vivienda: true });
    expect(r.motivo_no_elegible).toContain('salvo excepciones de las bases (separación, vivienda inadecuada…)');
  });
});

// ---------------------------------------------------------------- R7

describe('R7: estado', () => {
  it.each([
    ['proxima', /aún no abre/i],
    ['inscripcion_abierta', /abierta/i],
    ['inscripcion_cerrada', /cerrada/i],
    ['sorteo_adjudicacion', /sorteo|adjudicación/i],
    ['lista_espera_abierta', /lista de espera/i],
    ['finalizada', /finalizada/i],
    ['desconocido', /no (se )?(conoce|consta)|no disponible/i],
  ] as const)('%s es informativo', (estado, texto) => {
    const r = evaluar({}, {}, { estado });
    expect(regla(r, 'estado')).toMatchObject({ estado: 'INFORMATIVO', origen: null, sin_verificar: false });
    expect(regla(r, 'estado').explicacion).toMatch(texto);
    expect(r.veredicto).toBe('elegible');
  });

  it('dice si ya no aparece en la web de origen', () => {
    const r = evaluar({}, {}, { activa_en_fuente: false });
    expect(regla(r, 'estado').explicacion).toMatch(/ya no aparece/i);
  });
});

// ---------------------------------------------------------------- R9

describe('R9: condiciones', () => {
  it('no son reglas ni cambian el veredicto', () => {
    const r = evaluar({ condiciones: [{ texto: 'Residir en la vivienda', origen: 'regimen', sin_verificar: true }] });
    expect(r.veredicto).toBe('elegible');
    expect(r.reglas).toHaveLength(7);
  });
});

// ---------------------------------------------------------------- null combinations and aggregate

describe('todas las combinaciones de conocido, nulo, no exigido e incumplido', () => {
  type Estado = 'cumple' | 'desconocido' | 'no_exigido' | 'incumple';
  const ESTADOS_CASO: Estado[] = ['cumple', 'desconocido', 'no_exigido', 'incumple'];

  const requisitosProbados: {
    id: IdRegla;
    clave: keyof RequisitosCalculadora;
    cumple: Parametro<unknown>;
    incumple: Parametro<unknown>;
  }[] = [
    { id: 'ingresos_max', clave: 'ingresos_max_iprem', cumple: p(5.5), incumple: p(1) },
    { id: 'ingresos_min', clave: 'ingresos_min_iprem', cumple: p(1), incumple: p(5) },
    { id: 'tasa_esfuerzo', clave: 'tasa_esfuerzo_max', cumple: p(0.35), incumple: p(0.1) },
    { id: 'empadronamiento', clave: 'empadronamiento', cumple: p(padron()), incumple: p(padron({ anios_min: 20 })) },
    { id: 'edad', clave: 'edad', cumple: p(edad(18, 65)), incumple: p(edad(null, 20)) },
    { id: 'titularidad', clave: 'no_titular_vivienda', cumple: p(true), incumple: p(true) },
  ];

  const combinaciones = requisitosProbados.reduce<Estado[][]>(
    (previas) => previas.flatMap((c) => ESTADOS_CASO.map((e) => [...c, e])),
    [[]],
  );

  it(`las ${4 ** 6} dan la regla y el veredicto esperados`, () => {
    for (const combinacion of combinaciones) {
      const reqs: Record<string, unknown> = {};
      requisitosProbados.forEach((req, i) => {
        const estado = combinacion[i]!;
        reqs[req.clave] =
          estado === 'cumple'
            ? req.cumple
            : estado === 'incumple'
              ? req.incumple
              : estado === 'desconocido'
                ? desconocido()
                : noExigido();
      });
      // Only titularity fails through the entry rather than through the parameter.
      const titular = combinacion[5] === 'incumple';
      const r = evaluar(reqs as Partial<RequisitosCalculadora>, { titular_vivienda: titular });

      const esperadas = combinacion.map(
        (e): EstadoRegla => (e === 'desconocido' ? 'DESCONOCIDO' : e === 'incumple' ? 'NO_CUMPLE' : 'CUMPLE'),
      );
      expect(r.reglas.slice(0, 6).map((x) => x.estado), combinacion.join()).toEqual(esperadas);

      const primera = combinacion.indexOf('incumple');
      const veredicto =
        primera >= 0 ? 'no_elegible' : combinacion.includes('desconocido') ? 'posiblemente' : 'elegible';
      expect(r.veredicto, combinacion.join()).toBe(veredicto);
      expect(r.motivo_no_elegible, combinacion.join()).toBe(primera >= 0 ? r.reglas[primera]!.explicacion : null);
    }
  });

  it('todo nulo, en la promoción y en la persona: posiblemente', () => {
    const r = evaluar(
      {
        ingresos_min_iprem: desconocido(),
        ingresos_max_iprem: desconocido(),
        iprem_pagas: desconocido(),
        iprem_ejercicio: desconocido(),
        tasa_esfuerzo_max: desconocido(),
        empadronamiento: desconocido(),
        edad: desconocido(),
        no_titular_vivienda: desconocido(),
        coeficientes_ponderacion: desconocido(),
      },
      {
        municipio_empadronamiento: null,
        anios_empadronamiento: null,
        edad: null,
        titular_vivienda: null,
      },
      { tipologias: [{ dormitorios: null, renta_mensual_eur: null }], estado: 'desconocido' },
    );
    expect(r.veredicto).toBe('posiblemente');
    expect(r.reglas.slice(0, 6).every((x) => x.estado === 'DESCONOCIDO')).toBe(true);
    expect(r.avisos).toEqual([]);
  });
});

// ---------------------------------------------------------------- evaluarTodas

describe('evaluarTodas', () => {
  const ids = (
    promociones: PromocionCalculadora[],
    datos: Partial<EntradaCalculadora> = {},
    mostrarFinalizadas = false,
  ) => evaluarTodas(promociones, entrada(datos), IPREM, { mostrarFinalizadas }).map((r) => r.promocion.id);

  const renta = (valor: number | null) => [{ dormitorios: 2, renta_mensual_eur: valor }];

  it('excluye las finalizadas salvo que se pidan', () => {
    const lista = [promo({}, { id: 'a' }), promo({}, { id: 'b', estado: 'finalizada' })];
    expect(ids(lista)).toEqual(['a']);
    expect(ids(lista, {}, true)).toEqual(['a', 'b']);
  });

  it('ordena por veredicto', () => {
    const lista = [
      promo({ ingresos_max_iprem: p(1) }, { id: 'no' }),
      promo({ edad: desconocido() }, { id: 'quiza' }),
      promo({}, { id: 'si' }),
    ];
    expect(ids(lista)).toEqual(['si', 'quiza', 'no']);
  });

  it('dentro del grupo: inscripción abierta, renta ascendente, sin renta al final, nombre', () => {
    const lista = [
      promo({ tasa_esfuerzo_max: noExigido() }, { id: 'cerrada', estado: 'inscripcion_cerrada', tipologias: renta(100) }),
      promo({ tasa_esfuerzo_max: noExigido() }, { id: 'sin-renta-z', nombre: 'Zeta', tipologias: renta(null) }),
      promo({ tasa_esfuerzo_max: noExigido() }, { id: 'sin-renta-a', nombre: 'Álamo', tipologias: [] }),
      promo({ tasa_esfuerzo_max: noExigido() }, { id: 'cara', tipologias: renta(900) }),
      promo(
        { tasa_esfuerzo_max: noExigido() },
        { id: 'barata', tipologias: [...renta(null), ...renta(950), ...renta(400)] },
      ),
      promo({ tasa_esfuerzo_max: noExigido() }, { id: 'media-b', nombre: 'Beta', tipologias: renta(500) }),
      promo({ tasa_esfuerzo_max: noExigido() }, { id: 'media-a', nombre: 'Alfa', tipologias: renta(500) }),
    ];
    expect(ids(lista)).toEqual(['barata', 'media-a', 'media-b', 'cara', 'sin-renta-a', 'sin-renta-z', 'cerrada']);
  });

  it('dormitorios_min solo quita las que seguro no llegan', () => {
    const tipos = (...n: (number | null)[]) => n.map((dormitorios) => ({ dormitorios, renta_mensual_eur: 500 }));
    const lista = [
      promo({}, { id: 'pequena', tipologias: tipos(0, 1) }),
      promo({}, { id: 'grande', tipologias: tipos(1, 3) }),
      promo({}, { id: 'justa', tipologias: tipos(2) }),
      promo({}, { id: 'dudosa', tipologias: tipos(1, null) }),
      promo({}, { id: 'sin-tipos', tipologias: [] }),
    ];
    expect(ids(lista, { dormitorios_min: 2 }).sort()).toEqual(['dudosa', 'grande', 'justa', 'sin-tipos']);
    expect(ids(lista, { dormitorios_min: null })).toHaveLength(5);
  });

  it('dormitorios_min no cambia reglas ni veredictos', () => {
    const lista = [
      promo({}, { tipologias: [{ dormitorios: 1, renta_mensual_eur: 500 }, { dormitorios: 3, renta_mensual_eur: 2000 }] }),
    ];
    const sin = evaluarTodas(lista, entrada(), IPREM, { mostrarFinalizadas: false });
    const con = evaluarTodas(lista, entrada({ dormitorios_min: 3 }), IPREM, { mostrarFinalizadas: false });
    expect(con).toEqual(sin);
  });

  it('sin promociones', () => {
    expect(ids([])).toEqual([]);
  });
});
