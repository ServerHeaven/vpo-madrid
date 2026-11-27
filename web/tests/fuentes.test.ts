import { describe, expect, it } from 'vitest';
import type { Fuente } from '../src/lib/contratos';
import { resumirFuentes } from '../src/lib/fuentes';
import type { EstadoFuente, State } from '../src/lib/types';

const fuente = (id: string, cambios: Partial<Fuente> = {}): Fuente => ({
  id,
  nombre: id,
  operador: { id, nombre: id, tipo: 'otro' },
  url: 'https://example.invalid/',
  url_verificada: true,
  metodo: 'httpx',
  prioridad: 1,
  activa: true,
  intervalo_s: 3,
  timeout_s: 300,
  notas: null,
  ...cambios,
});

const registro = (estado: EstadoFuente['estado']): EstadoFuente => ({
  estado,
  ultima_ejecucion: '2026-11-27T14:00:00Z',
  ultimo_exito: null,
  fallos_consecutivos: estado === 'error' ? 1 : 0,
  ultimo_error: null,
  promociones_vistas: null,
  duracion_s: 1,
});

const state = (fuentes: State['fuentes']): State => ({
  schema_version: 1,
  ultima_ejecucion: null,
  fuentes,
  documentos: {},
  promo_ids: {},
});

describe('resumirFuentes', () => {
  it('distingue activas y no activas, con y sin registro', () => {
    const filas = resumirFuentes(
      [
        fuente('leida'),
        fuente('nueva'),
        fuente('futura', { activa: false }),
        fuente('retirada', { activa: false }),
      ],
      state({ leida: registro('degradado'), retirada: registro('ok') }),
      [],
    );

    expect(Object.fromEntries(filas.map((f) => [f.fuente.id, f.situacion]))).toEqual({
      leida: 'degradado',
      nueva: 'sin_ejecutar',
      futura: 'pendiente',
      retirada: 'desactivada',
    });
  });

  it('ordena activas primero, luego por prioridad y nombre, sin mutar la entrada', () => {
    const entrada = [
      fuente('z', { activa: false }),
      fuente('c', { prioridad: 2 }),
      fuente('b'),
      fuente('a'),
    ];

    const filas = resumirFuentes(entrada, state({}), []);

    expect(filas.map((f) => f.fuente.id)).toEqual(['a', 'b', 'c', 'z']);
    expect(entrada.map((f) => f.id)).toEqual(['z', 'c', 'b', 'a']);
  });

  it('cuenta las promociones publicadas de cada fuente aunque la lectura fallara', () => {
    const [fila] = resumirFuentes([fuente('a')], state({ a: registro('error') }), [
      { fuente_id: 'a' },
      { fuente_id: 'a' },
      { fuente_id: 'otra' },
    ]);

    expect(fila).toMatchObject({ situacion: 'error', publicadas: 2 });
  });
});
