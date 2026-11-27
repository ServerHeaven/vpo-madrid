import { describe, expect, it } from 'vitest';
import type { IndiceItem, IndiceTipologia } from '../src/lib/contratos';
import {
  SIN_FILTROS,
  aplicarFiltros,
  contarFiltros,
  escribirFiltros,
  evaluar,
  leerFiltros,
  opcionesDisponibles,
  rentaDesde,
  type Filtros,
} from '../src/lib/filters';

const HOY = '2026-11-27';

function tipo(cambio: Partial<IndiceTipologia> = {}): IndiceTipologia {
  return {
    dormitorios: 2,
    renta_mensual_eur: 600,
    renta_mensual_max_eur: null,
    garaje: 'incluido',
    trastero: 'opcional',
    ...cambio,
  };
}

function promo(id: string, cambio: Partial<IndiceItem> = {}): IndiceItem {
  return {
    id,
    nombre: id,
    operador: 'Operador',
    regimen: 'VPPB',
    programa: 'EMVS_MADRID',
    modalidad: 'alquiler',
    estado: 'inscripcion_abierta',
    activa_en_fuente: true,
    municipio_ine: '28079',
    municipio: 'Madrid',
    distrito: null,
    viviendas_total: 10,
    tipologias: [tipo()],
    inscripcion_fin: null,
    primera_deteccion: '2026-11-01',
    ...cambio,
  };
}

const filtros = (cambio: Partial<Filtros>): Filtros => ({ ...SIN_FILTROS, ...cambio });
const ids = (items: IndiceItem[], cambio: Partial<Filtros>) =>
  aplicarFiltros(items, filtros(cambio), HOY).visibles.map((p) => p.id);

/** Nothing is known beyond the mandatory fields. */
const desconocida = promo('desconocida', {
  regimen: 'DESCONOCIDO',
  programa: null,
  estado: 'desconocido',
  tipologias: [
    tipo({ dormitorios: null, renta_mensual_eur: null, garaje: 'desconocido', trastero: 'desconocido' }),
  ],
});

describe('filtros', () => {
  it('sin filtros muestra todo, también lo que no tiene datos', () => {
    expect(ids([promo('a'), desconocida], {})).toEqual(['a', 'desconocida']);
  });

  it('municipio (varios)', () => {
    const items = [
      promo('madrid'),
      promo('getafe', { municipio_ine: '28065' }),
      promo('rivas', { municipio_ine: '28123' }),
    ];
    expect(ids(items, { municipios: ['28065', '28123'] })).toEqual(['getafe', 'rivas']);
  });

  it('régimen, programa y estado', () => {
    const items = [
      promo('a'),
      promo('b', { regimen: 'VPPL', programa: 'PLAN_VIVE', estado: 'proxima' }),
    ];
    expect(ids(items, { regimenes: ['VPPL'] })).toEqual(['b']);
    expect(ids(items, { programas: ['PLAN_VIVE'] })).toEqual(['b']);
    expect(ids(items, { estados: ['proxima', 'inscripcion_abierta'] })).toEqual(['a', 'b']);
    expect(ids(items, { regimenes: ['VPPL'], programas: ['EMVS_MADRID'] })).toEqual([]);
  });

  it('solo con inscripción abierta', () => {
    const items = [promo('a'), promo('b', { estado: 'lista_espera_abierta' })];
    expect(ids(items, { soloAbiertas: true })).toEqual(['a']);
  });

  it('rango de renta, con los extremos incluidos', () => {
    const items = [
      promo('500', { tipologias: [tipo({ renta_mensual_eur: 500 })] }),
      promo('700', { tipologias: [tipo({ renta_mensual_eur: 700 })] }),
      promo('900', { tipologias: [tipo({ renta_mensual_eur: 900, renta_mensual_max_eur: 1200 })] }),
    ];
    expect(ids(items, { rentaMin: 700, rentaMax: 900 })).toEqual(['700', '900']);
    expect(ids(items, { rentaMax: 699 })).toEqual(['500']);
  });

  it('dormitorios es un mínimo', () => {
    const items = [promo('2d'), promo('3d', { tipologias: [tipo({ dormitorios: 3 })] })];
    expect(ids(items, { dormitorios: 3 })).toEqual(['3d']);
    expect(ids(items, { dormitorios: 2 })).toEqual(['2d', '3d']);
  });

  it('garaje y trastero', () => {
    const items = [
      promo('incluido'),
      promo('opcional', { tipologias: [tipo({ garaje: 'opcional', trastero: 'no' })] }),
      promo('no', { tipologias: [tipo({ garaje: 'no', trastero: 'incluido' })] }),
    ];
    expect(ids(items, { garaje: 'si' })).toEqual(['incluido', 'opcional']);
    expect(ids(items, { garaje: 'incluido' })).toEqual(['incluido']);
    expect(ids(items, { garaje: 'opcional' })).toEqual(['opcional']);
    expect(ids(items, { trastero: true })).toEqual(['incluido', 'no']);
  });

  it('los criterios de vivienda se exigen a una misma tipología', () => {
    const item = promo('mixta', {
      tipologias: [
        tipo({ dormitorios: 1, renta_mensual_eur: 400 }),
        tipo({ dormitorios: 3, renta_mensual_eur: 900 }),
      ],
    });
    expect(evaluar(item, filtros({ dormitorios: 3, rentaMax: 500 }))).toBe('no');
    expect(evaluar(item, filtros({ dormitorios: 3, rentaMax: 900 }))).toBe('si');
  });
});

describe('datos desconocidos', () => {
  it.each<[string, Partial<Filtros>]>([
    ['renta', { rentaMax: 1000 }],
    ['dormitorios', { dormitorios: 1 }],
    ['garaje', { garaje: 'si' }],
    ['trastero', { trastero: true }],
    ['régimen', { regimenes: ['VPPB'] }],
    ['programa', { programas: ['EMVS_MADRID'] }],
    ['estado', { estados: ['inscripcion_abierta'] }],
    ['abiertas', { soloAbiertas: true }],
  ])('nunca cuentan como coincidencia: %s', (_, cambio) => {
    const resultado = aplicarFiltros([promo('a'), desconocida], filtros(cambio), HOY);
    expect(resultado.visibles.map((p) => p.id)).toEqual(['a']);
    expect(resultado.sinDato).toBe(1);
  });

  it('sin tipologías no se puede saber', () => {
    expect(evaluar(promo('a', { tipologias: [] }), filtros({ dormitorios: 1 }))).toBe('sin_dato');
  });

  it('lo que incumple un dato conocido no se cuenta como falta de datos', () => {
    const resultado = aplicarFiltros([desconocida], filtros({ municipios: ['28065'], rentaMax: 1 }), HOY);
    expect(resultado).toEqual({ visibles: [], sinDato: 0 });
  });

  it('elegir el valor «no disponible» sí lo muestra', () => {
    expect(ids([promo('a'), desconocida], { regimenes: ['DESCONOCIDO'] })).toEqual(['desconocida']);
    expect(ids([promo('a'), desconocida], { estados: ['desconocido'] })).toEqual(['desconocida']);
  });
});

describe('orden', () => {
  it('por renta ascendente, sin dato al final', () => {
    const items = [
      promo('nada', { tipologias: [tipo({ renta_mensual_eur: null })] }),
      promo('cara', { tipologias: [tipo({ renta_mensual_eur: 900 })] }),
      promo('barata', { tipologias: [tipo({ renta_mensual_eur: 800 }), tipo({ renta_mensual_eur: 400 })] }),
    ];
    expect(ids(items, { orden: 'renta' })).toEqual(['barata', 'cara', 'nada']);
  });

  it('por renta usa solo las tipologías que cumplen', () => {
    const item = promo('a', {
      tipologias: [
        tipo({ dormitorios: 1, renta_mensual_eur: 300 }),
        tipo({ dormitorios: 3, renta_mensual_eur: 800 }),
      ],
    });
    expect(rentaDesde(item)).toBe(300);
    expect(rentaDesde(item, filtros({ dormitorios: 3 }))).toBe(800);
  });

  it('por cierre: próximos, luego pasados y al final sin fecha', () => {
    const items = [
      promo('sin-fecha'),
      promo('pasado-antiguo', { inscripcion_fin: '2026-01-01' }),
      promo('lejano', { inscripcion_fin: '2027-02-01' }),
      promo('pasado-reciente', { inscripcion_fin: '2026-11-26' }),
      promo('hoy', { inscripcion_fin: HOY }),
    ];
    expect(ids(items, { orden: 'cierre' })).toEqual([
      'hoy',
      'lejano',
      'pasado-reciente',
      'pasado-antiguo',
      'sin-fecha',
    ]);
  });

  it('por novedad, y a igualdad por nombre', () => {
    const items = [
      promo('Vallecas 10'),
      promo('Vallecas 9'),
      promo('Nueva', { primera_deteccion: '2026-11-20' }),
    ];
    expect(ids(items, {})).toEqual(['Nueva', 'Vallecas 9', 'Vallecas 10']);
    expect(items[0]!.id).toBe('Vallecas 10'); // the input is not mutated
  });
});

describe('opciones', () => {
  it('ofrece solo lo que hay en los datos', () => {
    const opciones = opcionesDisponibles([desconocida]);
    expect(opciones).toMatchObject({ renta: null, dormitorios: [], garaje: false, trastero: false });
    expect(opciones.programas).toEqual([]);
    expect(opciones.regimenes).toEqual(['DESCONOCIDO']);
    expect(opciones.municipios).toEqual([{ ine: '28079', nombre: 'Madrid' }]);
  });

  it('redondea el rango de renta y no ofrece uno vacío', () => {
    const items = [
      promo('a', {
        tipologias: [
          tipo({ renta_mensual_eur: 512 }),
          tipo({ renta_mensual_eur: 745, dormitorios: 3 }),
        ],
      }),
    ];
    expect(opcionesDisponibles(items)).toMatchObject({
      renta: { min: 510, max: 750 },
      dormitorios: [1, 2, 3],
      garaje: true,
    });
    expect(opcionesDisponibles([promo('b')]).renta).toBeNull();
  });
});

describe('URL', () => {
  const completos: Filtros = {
    municipios: ['28079', '28065'],
    regimenes: ['VPPB', 'VPPL'],
    programas: ['PLAN_VIVE'],
    estados: ['inscripcion_abierta', 'proxima'],
    rentaMin: 300,
    rentaMax: 900,
    dormitorios: 2,
    garaje: 'opcional',
    trastero: true,
    soloAbiertas: true,
    orden: 'cierre',
  };

  it('ida y vuelta', () => {
    expect(leerFiltros(escribirFiltros(completos))).toEqual(completos);
    expect(leerFiltros(`?${escribirFiltros(completos)}`)).toEqual(completos);
    expect(contarFiltros(completos)).toBe(9);
  });

  it('sin filtros no deja parámetros', () => {
    expect(escribirFiltros(SIN_FILTROS)).toBe('');
    expect(leerFiltros('')).toEqual(SIN_FILTROS);
    expect(contarFiltros(SIN_FILTROS)).toBe(0);
  });

  it('usa los nombres del diseño y admite listas con comas', () => {
    expect(escribirFiltros(filtros({ municipios: ['28079'], estados: ['inscripcion_abierta'] }))).toBe(
      'mun=28079&estado=inscripcion_abierta',
    );
    expect(leerFiltros('?mun=28079,28065&mun=28079').municipios).toEqual(['28079', '28065']);
  });

  it('ignora valores no válidos', () => {
    const consulta =
      '?mun=1,abc,08019&reg=XX,toString&prog=constructor&estado=nada&renta_min=-5&renta_max=1e3' +
      '&dorm=99&garaje=quizas&trastero=si&abierta=true&orden=azar&utm=x';
    expect(leerFiltros(consulta)).toEqual(SIN_FILTROS);
  });

  it('descarta un rango de renta invertido', () => {
    expect(leerFiltros('?renta_min=900&renta_max=300')).toEqual(SIN_FILTROS);
  });
});
