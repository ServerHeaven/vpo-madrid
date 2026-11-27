/** Internal links must always go through here so that `base` is applied (ARCHITECTURE.md §1). */
export function unirBase(base: string, ruta: string): string {
  const prefijo = base.endsWith('/') ? base : `${base}/`;
  return prefijo + ruta.replace(/^\/+/, '');
}

/** `url('')` is the home page; pages end in "/" (trailingSlash: 'always'), files do not. */
export function url(ruta = ''): string {
  return unirBase(import.meta.env.BASE_URL, ruta);
}

export const urlPromocion = (id: string): string => url(`promociones/${id}/`);
