import { describe, expect, it } from 'vitest';
import {
  correccionesDe,
  reglasAplicables,
  reglaVigente,
  resolverRequisitos,
  textoEdad,
  textoEmpadronamiento,
  textoMiembros,
  textoTasa,
} from '../src/lib/requisitos';
import type { Promocion, ReglaPrograma, Requisitos } from '../src/lib/types';

const SIN_REQUISITOS: Requisitos = {
  ingresos_min_iprem: null,
  ingresos_max_iprem: null,
  ingresos_por_miembros: null,
  iprem_pagas: null,
  iprem_ejercicio: null,
  tasa_esfuerzo_max: null,
  empadronamiento: null,
  edad: null,
  no_titular_vivienda: null,
  no_exigidos: [],
  otros: [],
};

interface Cambios extends Partial<Omit<Promocion, 'requisitos' | 'meta' | 'fechas'>> {
  requisitos?: Partial<Requisitos>;
  meta?: Partial<Promocion['meta']>;
  inicio?: string | null;
}

function promo({ requisitos, meta, inicio = null, ...resto }: Cambios = {}): Promocion {
  return {
    id: 'p',
    nombre: 'Prueba',
    operador: { id: 'op', nombre: 'Operador', tipo: 'otro' },
    fuente_id: 'f',
    regimen: 'VPPB',
    programa: 'PLAN_VIVE',
    modalidad: 'alquiler',
    estado: 'proxima',
    ubicacion: {
      municipio_ine: '28065',
      municipio: 'Getafe',
      distrito: null,
      direccion: null,
      lat: null,
      lon: null,
    },
    viviendas_total: null,
    tipologias: [],
    requisitos: { ...SIN_REQUISITOS, ...requisitos },
    fechas: { inscripcion_inicio: inicio, inscripcion_fin: null, sorteo: null, entrega_prevista: null },
    enlaces: { oficial: 'https://example.org/', solicitud: null, bases: [] },
    meta: {
      primera_deteccion: '2026-11-27',
      ultima_modificacion: '2026-11-27',
      activa_en_fuente: true,
      campos_pendientes: [],
      campos_override: [],
      procedencia: {},
      extractor_version: '0.3.0',
      ...meta,
    },
    ...resto,
  };
}

function regla(cambios: Partial<ReglaPrograma> & Pick<ReglaPrograma, 'clave' | 'tipo'>): ReglaPrograma {
  return {
    vigente_desde: null,
    vigente_hasta: null,
    ingresos_min_iprem: null,
    ingresos_max_iprem: null,
    iprem_pagas: null,
    tasa_esfuerzo_max: null,
    empadronamiento: null,
    edad: null,
    coeficientes_ponderacion: null,
    requisitos_no_comprobables: [],
    fuente: 'Fuente de prueba',
    verificado: true,
    notas: [],
    ...cambios,
  };
}

const PLAN_VIVE = regla({
  clave: 'PLAN_VIVE',
  tipo: 'programa',
  tasa_esfuerzo_max: 0.35,
  ingresos_max_iprem: 7,
  verificado: false,
  requisitos_no_comprobables: ['Inscripción en el registro'],
});
const VPPB = regla({
  clave: 'VPPB',
  tipo: 'regimen',
  ingresos_max_iprem: 5.5,
  requisitos_no_comprobables: ['Sin otra vivienda'],
});
const VPPA = regla({
  clave: 'VPPA',
  tipo: 'regimen',
  ingresos_max_iprem: 5.5,
  edad: { min: null, max: 35, tipo: 'requisito' },
  requisitos_no_comprobables: ['Condición VPPA'],
});
const REGLAS = [PLAN_VIVE, VPPB, VPPA];

describe('resolverRequisitos', () => {
  it('prefers the promotion, then the programme, then the régimen', () => {
    const propio = resolverRequisitos(promo({ requisitos: { ingresos_max_iprem: 4 } }), REGLAS);
    expect(propio.ingresos_max_iprem).toMatchObject({ valor: 4, origen: 'convocatoria', regla: null });

    const general = resolverRequisitos(promo(), REGLAS);
    expect(general.ingresos_max_iprem).toMatchObject({ valor: 7, origen: 'programa', regla: PLAN_VIVE });

    const regimen = resolverRequisitos(promo({ programa: null }), REGLAS);
    expect(regimen.ingresos_max_iprem).toMatchObject({ valor: 5.5, origen: 'regimen', regla: VPPB });
  });

  it('keeps null as unknown, never as not demanded', () => {
    const r = resolverRequisitos(promo(), REGLAS);
    expect(r.empadronamiento).toMatchObject({ valor: null, origen: 'desconocido' });
    expect(r.edad).toMatchObject({ valor: null, origen: 'desconocido' });
    expect(r.no_titular_vivienda).toMatchObject({ valor: null, origen: 'desconocido' });
  });

  it('honours no_exigidos over general values', () => {
    const r = resolverRequisitos(promo({ requisitos: { no_exigidos: ['tasa_esfuerzo_max'] } }), REGLAS);
    expect(r.tasa_esfuerzo_max).toMatchObject({ valor: null, origen: 'no_exigido', regla: null });
  });

  it('lets the table by household size prevail over the flat limits', () => {
    const tabla = [{ miembros_desde: 1, miembros_hasta: 2, min_iprem: null, max_iprem: 5.5 }];
    const r = resolverRequisitos(
      promo({ requisitos: { ingresos_por_miembros: tabla, ingresos_max_iprem: 3 } }),
      REGLAS,
    );
    expect(r.ingresos_min_iprem).toBeNull();
    expect(r.ingresos_max_iprem).toBeNull();
    expect(r.ingresos_por_miembros).toMatchObject({ valor: tabla, origen: 'convocatoria' });
  });

  it('never applies the VPPA entry to plain or unknown rent', () => {
    for (const modalidad of ['alquiler', null] as const) {
      const r = resolverRequisitos(promo({ regimen: 'VPPA', programa: null, modalidad }), REGLAS);
      expect(r.edad.origen).toBe('desconocido');
      expect(r.ingresos_max_iprem?.origen).toBe('desconocido');
      expect(r.condiciones).toEqual([]);
    }
  });

  it('applies the VPPA entry to rent with an option to buy', () => {
    const r = resolverRequisitos(
      promo({ regimen: 'VPPA', programa: null, modalidad: 'alquiler_opcion_compra' }),
      REGLAS,
    );
    expect(r.edad).toMatchObject({ origen: 'regimen', valor: { max: 35 } });
    expect(r.condiciones.map((c) => c.texto)).toEqual(['Condición VPPA']);
  });

  it('lists own conditions first and then the general ones, without repeats', () => {
    const r = resolverRequisitos(promo({ requisitos: { otros: ['Sin otra vivienda'] } }), REGLAS);
    expect(r.condiciones.map((c) => [c.texto, c.origen])).toEqual([
      ['Sin otra vivienda', 'convocatoria'],
      ['Inscripción en el registro', 'programa'],
    ]);
  });

  it('marks manual corrections with their reason', () => {
    const meta = {
      campos_override: ['/requisitos/edad/max', '/requisitos/no_exigidos'],
      procedencia: {
        '/requisitos/edad/max': {
          metodo: 'override' as const,
          confianza: 1,
          documento: null,
          pagina: null,
          evidencia: 'Bases p. 2',
          regla: null,
        },
      },
    };
    const r = resolverRequisitos(
      promo({
        meta,
        requisitos: { edad: { min: 18, max: 40, tipo: 'requisito' }, no_exigidos: ['empadronamiento'] },
      }),
      REGLAS,
    );
    expect(r.edad.origen).toBe('manual');
    expect(r.edad.correcciones).toEqual([{ puntero: '/requisitos/edad/max', motivo: 'Bases p. 2' }]);
    expect(r.empadronamiento.origen).toBe('no_exigido');
    expect(r.empadronamiento.correcciones.map((c) => c.puntero)).toEqual(['/requisitos/no_exigidos']);
    expect(r.no_titular_vivienda.correcciones).toEqual([]);
  });

  it('reports pending fields', () => {
    const r = resolverRequisitos(
      promo({ meta: { campos_pendientes: ['/requisitos/empadronamiento'] } }),
      REGLAS,
    );
    expect(r.empadronamiento.pendiente).toBe(true);
    expect(r.edad.pendiente).toBe(false);
  });
});

describe('vigencia', () => {
  const antigua = regla({ clave: 'VPPB', tipo: 'regimen', vigente_hasta: '2026-12-31' });
  const nueva = regla({ clave: 'VPPB', tipo: 'regimen', vigente_desde: '2027-01-01' });

  it('picks the version in force, both ends included', () => {
    expect(reglaVigente([antigua, nueva], 'regimen', 'VPPB', '2026-12-31')).toBe(antigua);
    expect(reglaVigente([antigua, nueva], 'regimen', 'VPPB', '2027-01-01')).toBe(nueva);
    expect(reglaVigente([nueva], 'regimen', 'VPPB', '2026-06-01')).toBeNull();
  });

  it('uses the opening date and falls back to the first detection', () => {
    expect(reglasAplicables(promo({ inicio: '2027-02-01' }), [antigua, nueva])).toEqual([nueva]);
    expect(reglasAplicables(promo(), [antigua, nueva])).toEqual([antigua]);
  });
});

describe('textos', () => {
  it('covers corrections made on a whole parent object', () => {
    const { meta } = promo({ meta: { campos_override: ['/requisitos'] } });
    expect(correccionesDe(meta, '/requisitos/edad')).toHaveLength(1);
    expect(correccionesDe(meta, '/fechas')).toHaveLength(0);
  });

  it('describes age, share of income, household size and census registration', () => {
    expect(textoEdad({ min: 18, max: 50, tipo: 'requisito' })).toBe('De 18 a 50 años');
    expect(textoEdad({ min: null, max: 35, tipo: 'cupo' })).toBe('Cupo reservado (no excluye): hasta 35 años');
    expect(textoEdad({ min: null, max: null, tipo: 'requisito' })).toBeNull();
    expect(textoTasa(0.35)).toBe('Máximo 35 % de los ingresos');
    expect(textoMiembros({ miembros_desde: 3, miembros_hasta: null, min_iprem: null, max_iprem: null })).toBe(
      '3 o más',
    );
    expect(
      textoEmpadronamiento(
        {
          ambito: 'municipio',
          municipio_ine: '28065',
          anios_min: 5,
          ininterrumpido: true,
          alternativa_trabajo: true,
        },
        promo(),
      ),
    ).toBe('Estar empadronado en Getafe, al menos 5 años de forma ininterrumpida, o trabajar allí');
  });
});
