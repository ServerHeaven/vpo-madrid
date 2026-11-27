// Emitted at build time as dist/data/index.json (ARCHITECTURE.md §7.2).
import type { APIRoute } from 'astro';
import { cargarDatos } from '../../lib/data';
import { construirIndice } from '../../lib/indice';

export const GET: APIRoute = () => {
  const datos = cargarDatos();
  return new Response(JSON.stringify(construirIndice(datos.promociones, datos.generado_en)), {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
};
