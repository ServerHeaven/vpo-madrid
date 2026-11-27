// Used from Astro pages (static) and from the Preact islands.
import type { EstadoPromocion } from '../lib/contratos';
import { ESTADOS } from '../lib/etiquetas';

const COLORES: Record<EstadoPromocion, string> = {
  inscripcion_abierta: 'bg-green-100 text-green-900',
  lista_espera_abierta: 'bg-green-100 text-green-900',
  proxima: 'bg-blue-100 text-blue-900',
  sorteo_adjudicacion: 'bg-amber-100 text-amber-900',
  inscripcion_cerrada: 'bg-slate-200 text-slate-900',
  finalizada: 'bg-slate-200 text-slate-900',
  desconocido: 'bg-slate-100 text-slate-700',
};

export default function BadgeEstado({ estado }: { estado: EstadoPromocion }) {
  return <span class={`etiqueta ${COLORES[estado]}`}>{ESTADOS[estado]}</span>;
}
