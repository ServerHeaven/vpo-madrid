// Joins the source catalogue (fuentes.json) with what the scraper recorded (state.json).
import type { Fuente } from './contratos';
import type { EstadoFuente, Promocion, State } from './types';

export type Situacion =
  | EstadoFuente['estado']
  | 'sin_ejecutar' // active, never read yet
  | 'pendiente' // not active, never read
  | 'desactivada'; // not active, but it was read before

export interface ResumenFuente {
  fuente: Fuente;
  situacion: Situacion;
  registro: EstadoFuente | null;
  /** Promotions of this source currently published on the site. */
  publicadas: number;
}

function situar(fuente: Fuente, registro: EstadoFuente | null): Situacion {
  if (!fuente.activa) return registro ? 'desactivada' : 'pendiente';
  return registro?.estado ?? 'sin_ejecutar';
}

/** Active sources first, then by priority and name. */
export function resumirFuentes(
  fuentes: Fuente[],
  state: State,
  promociones: Pick<Promocion, 'fuente_id'>[],
): ResumenFuente[] {
  return [...fuentes]
    .sort(
      (a, b) =>
        Number(b.activa) - Number(a.activa) ||
        a.prioridad - b.prioridad ||
        a.nombre.localeCompare(b.nombre, 'es'),
    )
    .map((fuente) => {
      const registro = state.fuentes[fuente.id] ?? null;
      return {
        fuente,
        situacion: situar(fuente, registro),
        registro,
        publicadas: promociones.filter((p) => p.fuente_id === fuente.id).length,
      };
    });
}
