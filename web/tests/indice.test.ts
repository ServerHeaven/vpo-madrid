import { describe, expect, it } from 'vitest';
import { cargarDatos } from '../src/lib/data';
import { construirIndice } from '../src/lib/indice';
import type { Promocion } from '../src/lib/types';
import { GET } from '../src/pages/data/index.json';

const CLAVES = [
  'activa_en_fuente',
  'distrito',
  'estado',
  'id',
  'inscripcion_fin',
  'modalidad',
  'municipio',
  'municipio_ine',
  'nombre',
  'operador',
  'primera_deteccion',
  'programa',
  'regimen',
  'tipologias',
  'viviendas_total',
];

describe('construirIndice', () => {
  const datos = cargarDatos();

  it('reduce cada promoción a los campos del contrato', () => {
    const base = datos.promociones[0]!;
    const promocion: Promocion = {
      ...base,
      modalidad: null,
      tipologias: [
        {
          dormitorios: 2,
          superficie_util_m2: 60,
          renta_mensual_eur: 500,
          renta_mensual_max_eur: 650,
          num_viviendas: 4,
          garaje: { disponibilidad: 'incluido', precio_mensual_eur: null },
          trastero: { disponibilidad: 'opcional', precio_mensual_eur: 20 },
          adaptada_pmr: null,
        },
      ],
    };

    const indice = construirIndice([promocion], '2026-11-27T00:00:00Z');

    expect(indice.schema_version).toBe(1);
    expect(indice.generado_en).toBe('2026-11-27T00:00:00Z');
    const [item] = indice.promociones;
    expect(Object.keys(item!).sort()).toEqual(CLAVES);
    expect(item).toMatchObject({
      id: base.id,
      operador: base.operador.nombre,
      modalidad: null,
      municipio_ine: base.ubicacion.municipio_ine,
      activa_en_fuente: base.meta.activa_en_fuente,
      inscripcion_fin: base.fechas.inscripcion_fin,
      primera_deteccion: base.meta.primera_deteccion,
    });
    expect(item!.tipologias).toEqual([
      {
        dormitorios: 2,
        renta_mensual_eur: 500,
        renta_mensual_max_eur: 650,
        garaje: 'incluido',
        trastero: 'opcional',
      },
    ]);
  });

  it('conserva todas las promociones en su orden y es ligero (§7.2: 1–2 KB por promoción)', () => {
    const indice = construirIndice(datos.promociones, datos.generado_en);
    expect(indice.promociones.map((p) => p.id)).toEqual(datos.promociones.map((p) => p.id));
    expect(JSON.stringify(indice).length / indice.promociones.length).toBeLessThan(2048);
  });

  it('se publica como data/index.json', async () => {
    const respuesta = await GET({} as Parameters<typeof GET>[0]);
    expect(respuesta.headers.get('Content-Type')).toContain('application/json');
    expect(await respuesta.json()).toEqual(construirIndice(datos.promociones, datos.generado_en));
  });
});
