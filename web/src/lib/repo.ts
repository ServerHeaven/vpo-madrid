export const REPO_URL = 'https://github.com/ServerHeaven/vpo-madrid';

/** "¿Ves un error?": opens the correction form with the promotion id prefilled. */
export function urlCorreccion(promoId: string, nombre: string): string {
  const consulta = new URLSearchParams({
    template: 'correccion-dato.yml',
    title: `Corrección de datos: ${nombre}`,
    id: promoId,
  });
  return `${REPO_URL}/issues/new?${consulta}`;
}

/** A file of the repository as shown on GitHub, e.g. urlArchivo('data/overrides.json'). */
export const urlArchivo = (ruta: string): string => `${REPO_URL}/blob/main/${ruta}`;
