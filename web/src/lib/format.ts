// es-ES formatting shared by pages and islands. Pure and safe in the browser.

const euros = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 2 });
const numero = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 });
const diaMadrid = new Intl.DateTimeFormat('es-ES', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  timeZone: 'Europe/Madrid',
});

export const formatEur = (valor: number): string => euros.format(valor);
export const formatNumero = (valor: number): string => numero.format(valor);

/** "2026-06-11" → "11/06/2026". No time zone conversion: it is a calendar date. */
export function formatFecha(iso: string): string {
  const [anio, mes, dia] = iso.slice(0, 10).split('-');
  return `${dia}/${mes}/${anio}`;
}

/** UTC timestamp → calendar day in Madrid. */
export const formatMarcaTiempo = (iso: string): string => diaMadrid.format(new Date(iso));

/** "2027", "2027-T2", "2027-06" → "2027", "2.º trimestre de 2027", "06/2027". */
export function formatEntrega(valor: string): string {
  const [anio, resto] = valor.split('-');
  if (!resto) return anio!;
  return resto.startsWith('T') ? `${resto.slice(1)}.º trimestre de ${anio}` : `${resto}/${anio}`;
}

/** Rent of one dwelling type, or null when unknown. */
export function formatRenta(renta: number | null, rentaMax: number | null = null): string | null {
  if (renta === null) return null;
  if (rentaMax !== null && rentaMax !== renta) return `${formatEur(renta)} – ${formatEur(rentaMax)}/mes`;
  return `${formatEur(renta)}/mes`;
}
