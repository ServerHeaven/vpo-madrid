import { describe, expect, it } from 'vitest';
import { enlaceSeguro, ultimaComprobacion } from '../src/lib/comprobacion';
import type { DocumentoEstado, OverridesFile, Promocion, State } from '../src/lib/types';

const promo = (oficial: string, fuente_id = 'plan-vive-cam', id = 'p'): Promocion =>
  ({ id, fuente_id, enlaces: { oficial, solicitud: null, bases: [] } }) as unknown as Promocion;

const documento = (url: string, fuente_id: string, ultima_comprobacion: string) =>
  ({ url, fuente_id, ultima_comprobacion }) as DocumentoEstado;

const state = {
  fuentes: { 'plan-vive-cam': { ultimo_exito: '2026-11-26T05:00:00Z' } },
  documentos: {
    a: documento('https://www.comunidad.madrid/plan-vive', 'plan-vive-cam', '2026-11-27'),
    b: documento('https://example.org/x', 'otra', '2026-11-01'),
  },
} as unknown as State;

const overrides = { promociones_manuales: [] } as unknown as OverridesFile;

describe('ultimaComprobacion', () => {
  it('matches the page ignoring the #fragment of the promotion link', () => {
    const p = promo('https://www.comunidad.madrid/plan-vive#getafe');
    expect(ultimaComprobacion(p, state, overrides)).toEqual({ tipo: 'ficha', fecha: '2026-11-27' });
  });

  it('does not borrow the record of another source', () => {
    const p = promo('https://example.org/x');
    expect(ultimaComprobacion(p, state, overrides)).toEqual({ tipo: 'fuente', fecha: '2026-11-26T05:00:00Z' });
  });

  it('says so when there is no record at all', () => {
    const p = promo('https://example.org/y', 'desconocida');
    expect(ultimaComprobacion(p, state, overrides)).toEqual({ tipo: 'sin_dato' });
  });

  it('never claims to have checked a manual promotion', () => {
    const p = promo('https://www.comunidad.madrid/plan-vive', 'plan-vive-cam', 'a-mano');
    const manual = { promociones_manuales: [p] } as unknown as OverridesFile;
    expect(ultimaComprobacion(p, state, manual)).toEqual({ tipo: 'manual' });
  });
});

describe('enlaceSeguro', () => {
  it('only accepts http and https', () => {
    expect(enlaceSeguro('https://example.org/a b')).toBe('https://example.org/a%20b');
    expect(enlaceSeguro('javascript:alert(1)')).toBeNull();
    expect(enlaceSeguro('data:text/html,x')).toBeNull();
    expect(enlaceSeguro('no es una url')).toBeNull();
    expect(enlaceSeguro(null)).toBeNull();
  });
});
