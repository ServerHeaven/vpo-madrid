import BadgeEstado from '../components/BadgeEstado';
import type { IndiceItem } from '../lib/contratos';
import { DISPONIBILIDADES, MODALIDADES, PROGRAMAS, REGIMENES, SIN_DATO } from '../lib/etiquetas';
import { rentaDesde } from '../lib/filters';
import { formatEur, formatFecha, formatNumero } from '../lib/format';
import { urlPromocion } from '../lib/rutas';

function resumenDormitorios(p: IndiceItem): string | null {
  const valores = [...new Set(p.tipologias.flatMap((t) => (t.dormitorios === null ? [] : [t.dormitorios])))];
  if (valores.length === 0) return null;
  const partes = valores.sort((a, b) => a - b).map((n) => (n === 0 ? 'estudio' : String(n)));
  return partes.join(', ');
}

/** Distinct known values; null when nothing is known, so the row is left out. */
function resumenAnejo(p: IndiceItem, anejo: 'garaje' | 'trastero'): string | null {
  const valores = [...new Set(p.tipologias.map((t) => t[anejo]))].filter((v) => v !== 'desconocido');
  return valores.length ? valores.map((v) => DISPONIBILIDADES[v]).join(' / ') : null;
}

export default function TarjetaPromo({ promo }: { promo: IndiceItem }) {
  const renta = rentaDesde(promo);
  const dormitorios = resumenDormitorios(promo);
  const garaje = resumenAnejo(promo, 'garaje');
  const trastero = resumenAnejo(promo, 'trastero');
  const clasificacion = [
    promo.programa && PROGRAMAS[promo.programa],
    REGIMENES[promo.regimen],
    promo.modalidad ? MODALIDADES[promo.modalidad] : 'Modalidad no disponible',
  ];

  return (
    <article class="tarjeta relative flex h-full flex-col gap-2 focus-within:border-blue-700 hover:border-blue-700">
      <div class="flex flex-wrap gap-2">
        <BadgeEstado estado={promo.estado} />
        {!promo.activa_en_fuente && (
          <span class="etiqueta bg-red-100 text-red-900">Ya no aparece en la fuente</span>
        )}
      </div>
      <h2 class="text-lg font-bold">
        {/* The pseudo-element makes the whole card the link target. */}
        <a class="text-blue-900 underline underline-offset-2 after:absolute after:inset-0" href={urlPromocion(promo.id)}>
          {promo.nombre}
        </a>
      </h2>
      <p class="text-slate-700">
        {promo.municipio}
        {promo.distrito && ` · ${promo.distrito}`}
        <br />
        {promo.operador}
      </p>
      <p class="text-sm text-slate-700">{clasificacion.filter(Boolean).join(' · ')}</p>
      <dl class="mt-auto grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 border-t border-slate-200 pt-2 text-sm">
        <dt class="text-slate-600">Renta</dt>
        <dd class="font-semibold">{renta === null ? SIN_DATO : `Desde ${formatEur(renta)}/mes`}</dd>
        <dt class="text-slate-600">Dormitorios</dt>
        <dd>{dormitorios ?? SIN_DATO}</dd>
        {promo.viviendas_total !== null && (
          <>
            <dt class="text-slate-600">Viviendas</dt>
            <dd>{formatNumero(promo.viviendas_total)}</dd>
          </>
        )}
        {garaje && (
          <>
            <dt class="text-slate-600">Garaje</dt>
            <dd>{garaje}</dd>
          </>
        )}
        {trastero && (
          <>
            <dt class="text-slate-600">Trastero</dt>
            <dd>{trastero}</dd>
          </>
        )}
        {promo.inscripcion_fin && (
          <>
            <dt class="text-slate-600">Cierre</dt>
            <dd>{formatFecha(promo.inscripcion_fin)}</dd>
          </>
        )}
      </dl>
    </article>
  );
}
