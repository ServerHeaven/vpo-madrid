import { describe, expect, it } from 'vitest';
import type { Datos } from '../src/lib/contratos';
import { cargarDatos } from '../src/lib/data';
import {
  buscarMunicipio,
  CAMPOS_VACIOS,
  leerCampos,
  leerNumero,
  type Campos,
} from '../src/islands/CalculadoraEntrada';
import { FUERA_DE_LA_COMUNIDAD } from '../src/lib/contratos-calculadora';
import { construirDatosCalculadora } from '../src/lib/datos-calculadora';
import { reglasAplicables, resolverRequisitos } from '../src/lib/requisitos';
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

interface Cambios extends Partial<Omit<Promocion, 'requisitos' | 'meta'>> {
  requisitos?: Partial<Requisitos>;
  meta?: Partial<Promocion['meta']>;
}

function promo({ requisitos, meta, ...resto }: Cambios = {}): Promocion {
  return {
    id: 'p',
    nombre: 'Prueba',
    operador: { id: 'op', nombre: 'Operador de prueba', tipo: 'otro' },
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
    fechas: { inscripcion_inicio: null, inscripcion_fin: null, sorteo: null, entrega_prevista: null },
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
  requisitos_no_comprobables: ['Inscripción en el registro'],
  verificado: false,
});
const VPPB = regla({
  clave: 'VPPB',
  tipo: 'regimen',
  ingresos_max_iprem: 5.5,
  requisitos_no_comprobables: ['No ser titular de otra vivienda'],
});
const VPPA = regla({
  clave: 'VPPA',
  tipo: 'regimen',
  ingresos_max_iprem: 5.5,
  edad: { min: null, max: 35, tipo: 'requisito' },
  requisitos_no_comprobables: ['Condición VPPA'],
});

function datos(promociones: Promocion[], programas: ReglaPrograma[] = [PLAN_VIVE, VPPB, VPPA]): Datos {
  return {
    generado_en: '2026-11-27T00:00:00Z',
    promociones,
    state: {} as Datos['state'],
    fuentes: [],
    programas,
    overrides: {} as Datos['overrides'],
    iprem: [
      { anio: 2025, mensual: 600, anual_12: 7200, anual_14: 8400, fuente: 'BOE', verificado: true },
    ],
    municipios: [{ ine: '28065', nombre: 'Getafe', nombre_ine: 'Getafe' }],
  };
}

const unica = (p: Promocion, programas?: ReglaPrograma[]) =>
  construirDatosCalculadora(datos([p], programas)).promociones[0]!;

describe('construirDatosCalculadora', () => {
  it('reduce la entrada a los campos del contrato', () => {
    const salida = construirDatosCalculadora(
      datos([
        promo({
          tipologias: [
            {
              dormitorios: 2,
              superficie_util_m2: 60,
              renta_mensual_eur: 500,
              renta_mensual_max_eur: 650,
              num_viviendas: 4,
              garaje: { disponibilidad: 'incluido', precio_mensual_eur: null },
              trastero: { disponibilidad: 'no', precio_mensual_eur: null },
              adaptada_pmr: null,
            },
          ],
        }),
      ]),
    );

    expect(Object.keys(salida).sort()).toEqual(['generado_en', 'iprem', 'municipios', 'promociones']);
    expect(salida.generado_en).toBe('2026-11-27T00:00:00Z');
    expect(salida.iprem).toEqual([{ anio: 2025, anual_12: 7200, anual_14: 8400, verificado: true }]);
    expect(salida.municipios).toEqual([{ ine: '28065', nombre: 'Getafe' }]);

    const [p] = salida.promociones;
    expect(Object.keys(p!).sort()).toEqual([
      'activa_en_fuente',
      'estado',
      'id',
      'municipio',
      'municipio_ine',
      'nombre',
      'operador',
      'requisitos',
      'tipologias',
    ]);
    expect(p).toMatchObject({
      id: 'p',
      operador: 'Operador de prueba',
      municipio_ine: '28065',
      municipio: 'Getafe',
      estado: 'proxima',
      activa_en_fuente: true,
    });
    expect(p!.tipologias).toEqual([{ dormitorios: 2, renta_mensual_eur: 500 }]);
    expect(Object.keys(p!.requisitos).sort()).toEqual([
      'coeficientes_ponderacion',
      'condiciones',
      'edad',
      'empadronamiento',
      'ingresos_max_iprem',
      'ingresos_min_iprem',
      'ingresos_por_miembros',
      'iprem_ejercicio',
      'iprem_pagas',
      'no_titular_vivienda',
      'tasa_esfuerzo_max',
    ]);
    expect(Object.keys(p!.requisitos.tasa_esfuerzo_max).sort()).toEqual(['origen', 'sin_verificar', 'valor']);
  });

  it('marca el origen y si el valor general está sin verificar', () => {
    const r = unica(
      promo({
        requisitos: { edad: { min: 18, max: null, tipo: 'requisito' }, no_exigidos: ['empadronamiento'] },
      }),
    ).requisitos;

    expect(r.edad).toEqual({
      valor: { min: 18, max: null, tipo: 'requisito' },
      origen: 'convocatoria',
      sin_verificar: false,
    });
    expect(r.tasa_esfuerzo_max).toEqual({ valor: 0.35, origen: 'programa', sin_verificar: true });
    expect(r.ingresos_max_iprem).toEqual({ valor: 5.5, origen: 'regimen', sin_verificar: false });
    expect(r.empadronamiento).toEqual({ valor: null, origen: 'no_exigido', sin_verificar: false });
    expect(r.ingresos_min_iprem).toEqual({ valor: null, origen: 'desconocido', sin_verificar: false });
    expect(r.ingresos_por_miembros).toBeNull();
  });

  it('un valor corregido a mano no se marca como sin verificar', () => {
    const r = unica(
      promo({
        requisitos: { tasa_esfuerzo_max: 0.3 },
        meta: { campos_override: ['/requisitos/tasa_esfuerzo_max'] },
      }),
    ).requisitos;
    expect(r.tasa_esfuerzo_max).toEqual({ valor: 0.3, origen: 'manual', sin_verificar: false });
  });

  it('con tabla por miembros deja en null los límites planos', () => {
    const tabla = [{ miembros_desde: 1, miembros_hasta: null, min_iprem: 1, max_iprem: 4 }];
    const r = unica(promo({ requisitos: { ingresos_por_miembros: tabla } })).requisitos;
    expect(r.ingresos_por_miembros).toEqual({ valor: tabla, origen: 'convocatoria', sin_verificar: false });
    expect(r.ingresos_min_iprem).toBeNull();
    expect(r.ingresos_max_iprem).toBeNull();
  });

  it('no aplica los valores de VPPA sin opción de compra (ADR-002 A)', () => {
    const sin = unica(promo({ regimen: 'VPPA', programa: null, modalidad: 'alquiler' })).requisitos;
    expect(sin.edad.origen).toBe('desconocido');
    expect(sin.ingresos_max_iprem?.origen).toBe('desconocido');
    expect(sin.condiciones).toEqual([]);

    const con = unica(
      promo({ regimen: 'VPPA', programa: null, modalidad: 'alquiler_opcion_compra' }),
    ).requisitos;
    expect(con.edad).toEqual({
      valor: { min: null, max: 35, tipo: 'requisito' },
      origen: 'regimen',
      sin_verificar: false,
    });
    expect(con.condiciones).toEqual([{ texto: 'Condición VPPA', origen: 'regimen', sin_verificar: false }]);
  });

  it('toma los coeficientes de ponderación de programas.json, el programa primero', () => {
    const programa = { ...PLAN_VIVE, coeficientes_ponderacion: { '1': 0.9 } };
    const regimen = { ...VPPB, coeficientes_ponderacion: { '1': 0.8 } };

    expect(unica(promo(), [programa, regimen]).requisitos.coeficientes_ponderacion).toEqual({
      valor: { '1': 0.9 },
      origen: 'programa',
      sin_verificar: true,
    });
    expect(unica(promo(), [PLAN_VIVE, regimen]).requisitos.coeficientes_ponderacion).toEqual({
      valor: { '1': 0.8 },
      origen: 'regimen',
      sin_verificar: false,
    });
    expect(unica(promo()).requisitos.coeficientes_ponderacion).toEqual({
      valor: null,
      origen: 'desconocido',
      sin_verificar: false,
    });
    // Same ADR-002 A exclusion as the rest of the defaults.
    const vppa = { ...VPPA, coeficientes_ponderacion: { '1': 0.8 } };
    expect(
      unica(promo({ regimen: 'VPPA', programa: null }), [vppa]).requisitos.coeficientes_ponderacion.valor,
    ).toBeNull();
  });

  it('reúne las condiciones de la convocatoria y las generales con su verificación', () => {
    const r = unica(promo({ requisitos: { otros: ['Ser mayor de edad'] } })).requisitos;
    expect(r.condiciones).toEqual([
      { texto: 'Ser mayor de edad', origen: 'convocatoria', sin_verificar: false },
      { texto: 'Inscripción en el registro', origen: 'programa', sin_verificar: true },
      { texto: 'No ser titular de otra vivienda', origen: 'regimen', sin_verificar: false },
    ]);
  });
});

describe('construirDatosCalculadora con los datos reales', () => {
  const reales = cargarDatos();
  const salida = construirDatosCalculadora(reales);

  it('conserva todas las promociones, municipios e IPREM', () => {
    expect(salida.promociones.map((p) => p.id)).toEqual(reales.promociones.map((p) => p.id));
    expect(salida.municipios).toHaveLength(reales.municipios.length);
    expect(salida.iprem.map((i) => i.anio)).toEqual(reales.iprem.map((i) => i.anio));
  });

  it('resuelve cada requisito igual que las fichas', () => {
    reales.promociones.forEach((p, i) => {
      const ficha = resolverRequisitos(p, reales.programas);
      const calculadora = salida.promociones[i]!.requisitos;
      for (const clave of [
        'ingresos_min_iprem',
        'ingresos_max_iprem',
        'ingresos_por_miembros',
        'iprem_pagas',
        'iprem_ejercicio',
        'tasa_esfuerzo_max',
        'empadronamiento',
        'edad',
        'no_titular_vivienda',
      ] as const) {
        const esperado = ficha[clave];
        if (esperado === null) expect(calculadora[clave]).toBeNull();
        else expect(calculadora[clave]).toMatchObject({ valor: esperado.valor, origen: esperado.origen });
      }
      expect(calculadora.condiciones.map((c) => c.texto)).toEqual(ficha.condiciones.map((c) => c.texto));
      const coeficientes = reglasAplicables(p, reales.programas).find((r) => r.coeficientes_ponderacion);
      expect(calculadora.coeficientes_ponderacion.valor).toEqual(coeficientes?.coeficientes_ponderacion ?? null);
    });
  });

  it('es ligero: menos de 3 KB por promoción', () => {
    expect(JSON.stringify(salida.promociones).length / salida.promociones.length).toBeLessThan(3072);
  });
});

// The form of the calculator: a blank box must reach the engine as null, never as 0 or false.
describe('lectura del formulario', () => {
  const municipios = [
    { ine: '28065', nombre: 'Getafe' },
    { ine: '28005', nombre: 'Alcalá de Henares' },
    { ine: '28127', nombre: 'Las Rozas de Madrid' },
  ];
  const minimos: Campos = { ...CAMPOS_VACIOS, ingresos: '28.500', miembros: '2', ejercicio: '2025' };

  it('deja en null todo lo que no se ha rellenado', () => {
    expect(leerCampos(minimos, municipios).entrada).toEqual({
      ingresos_anuales: 28500,
      ingresos_estimados: false,
      ejercicio: 2025,
      miembros: 2,
      municipio_empadronamiento: null,
      anios_empadronamiento: null,
      municipio_trabajo: null,
      anios_trabajo: null,
      edad: null,
      titular_vivienda: null,
      dormitorios_min: null,
    });
  });

  it('exige ingresos y miembros y no adivina lo que no entiende', () => {
    expect(Object.keys(leerCampos({ ...CAMPOS_VACIOS, ejercicio: '2025' }, municipios).errores!)).toEqual([
      'ingresos',
      'miembros',
    ]);
    const malos = { ...minimos, empadronamiento: 'Getaf', aniosTrabajo: 'tres', edad: '15' };
    expect(Object.keys(leerCampos(malos, municipios).errores!).sort()).toEqual([
      'aniosTrabajo',
      'edad',
      'empadronamiento',
    ]);
  });

  it('lee cantidades escritas en español', () => {
    expect(['30000', '30.000', '30 000,50 €', '2,5', '2.5', '0'].map(leerNumero)).toEqual([
      30000, 30000, 30000.5, 2.5, 2.5, 0,
    ]);
    expect(['', '-1', '30,000.00', '1.2345', 'mil'].map(leerNumero)).toEqual([null, null, null, null, null]);
  });

  it('reconoce el municipio sin tildes ni artículo', () => {
    expect(buscarMunicipio(' alcala de henares ', municipios)).toBe('28005');
    expect(buscarMunicipio('Rozas de Madrid', municipios)).toBe('28127');
    expect(buscarMunicipio('Alcalá', municipios)).toBeNull();
  });

  it('traduce «fuera», la titularidad y los dormitorios', () => {
    const campos: Campos = {
      ...minimos,
      empadronamientoFuera: true,
      aniosEmpadronamiento: '4',
      trabajo: 'Getafe',
      aniosTrabajo: '1,5',
      titular: 'no',
      dormitorios: '2',
      edad: '34',
    };
    expect(leerCampos(campos, municipios).entrada).toMatchObject({
      municipio_empadronamiento: FUERA_DE_LA_COMUNIDAD,
      anios_empadronamiento: null,
      municipio_trabajo: '28065',
      anios_trabajo: 1.5,
      titular_vivienda: false,
      dormitorios_min: 2,
      edad: 34,
    });
  });

  it('marca como estimados los ingresos calculados desde el bruto', () => {
    const { entrada } = leerCampos({ ...minimos, ingresos: '30.000', soloBruto: true }, municipios);
    // 30000 − 6.35 % − 2000
    expect(entrada).toMatchObject({ ingresos_anuales: 26095, ingresos_estimados: true });
  });
});
