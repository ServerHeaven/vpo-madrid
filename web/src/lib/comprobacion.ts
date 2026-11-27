// Traceability helpers for the detail page. Pure.
import type { DocumentoEstado, OverridesFile, Promocion, State } from './types';

export type Comprobacion =
  /** This promotion's own page was checked (calendar date). */
  | { tipo: 'ficha'; fecha: string }
  /** No record of the page: last successful read of the whole source (UTC timestamp). */
  | { tipo: 'fuente'; fecha: string }
  /** Added by hand: nothing checks it automatically. */
  | { tipo: 'manual' }
  | { tipo: 'sin_dato' };

const sinFragmento = (url: string): string => url.split('#')[0]!;

/** The state.json record of a URL for one source. Fragments are ignored on both sides. */
export function documentoDe(url: string, fuenteId: string, state: State): DocumentoEstado | null {
  const buscada = sinFragmento(url);
  const candidatos = Object.values(state.documentos).filter(
    (d) => d.fuente_id === fuenteId && sinFragmento(d.url) === buscada,
  );
  candidatos.sort((a, b) => b.ultima_comprobacion.localeCompare(a.ultima_comprobacion));
  return candidatos[0] ?? null;
}

export function ultimaComprobacion(promo: Promocion, state: State, overrides: OverridesFile): Comprobacion {
  if (overrides.promociones_manuales.some((p) => p.id === promo.id)) return { tipo: 'manual' };
  const documento = documentoDe(promo.enlaces.oficial, promo.fuente_id, state);
  if (documento) return { tipo: 'ficha', fecha: documento.ultima_comprobacion };
  const exito = state.fuentes[promo.fuente_id]?.ultimo_exito;
  return exito ? { tipo: 'fuente', fecha: exito } : { tipo: 'sin_dato' };
}

/** Scraped and hand-written URLs are untrusted: only http(s) ones become links. */
export function enlaceSeguro(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const { protocol, href } = new URL(url);
    return protocol === 'http:' || protocol === 'https:' ? href : null;
  } catch {
    return null;
  }
}
