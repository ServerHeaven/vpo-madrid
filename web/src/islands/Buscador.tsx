// Search island. The server renders the full list, so the page is readable without JS;
// the controls carry the class "solo-js", which index.astro hides inside <noscript>.
// Filters live in memory and in the URL only: no network requests and no storage.
import type { ComponentChildren } from 'preact';
import { useEffect, useMemo, useState } from 'preact/hooks';
import type { IndiceItem } from '../lib/contratos';
import { ESTADOS, PROGRAMAS, REGIMENES } from '../lib/etiquetas';
import {
  FILTROS_GARAJE,
  ORDENES,
  SIN_FILTROS,
  aplicarFiltros,
  contarFiltros,
  escribirFiltros,
  leerFiltros,
  opcionesDisponibles,
  type FiltroGaraje,
  type Filtros,
  type Orden,
} from '../lib/filters';
import { formatEur } from '../lib/format';
import TarjetaPromo from './TarjetaPromo';

const hoyEnMadrid = (): string => new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Madrid' });

const CASILLA = 'flex min-h-11 cursor-pointer items-center gap-3';
const SELECTOR = 'min-h-11 w-full rounded-md border border-slate-500 bg-white px-2';

function Casilla(props: { texto: string; marcada: boolean; alCambiar: (marcada: boolean) => void }) {
  return (
    <label class={CASILLA}>
      <input
        type="checkbox"
        class="size-5 shrink-0"
        checked={props.marcada}
        onChange={(e) => props.alCambiar(e.currentTarget.checked)}
      />
      <span>{props.texto}</span>
    </label>
  );
}

function Grupo({ leyenda, children }: { leyenda: string; children: ComponentChildren }) {
  return (
    <fieldset class="border-t border-slate-200 pt-3">
      <legend class="pr-2 font-semibold">{leyenda}</legend>
      {children}
    </fieldset>
  );
}

/** Multiple choice. Selected values missing from the data stay listed so they can be cleared. */
function Seleccion<T extends string>(props: {
  leyenda: string;
  valores: T[];
  seleccion: T[];
  texto: (valor: T) => string;
  alCambiar: (seleccion: T[]) => void;
  conDesplazamiento?: boolean;
}) {
  const valores = [...props.valores, ...props.seleccion.filter((v) => !props.valores.includes(v))];
  if (valores.length === 0) return null;
  return (
    <Grupo leyenda={props.leyenda}>
      <div class={props.conDesplazamiento ? 'max-h-60 overflow-y-auto p-1' : ''}>
        {valores.map((valor) => (
          <Casilla
            key={valor}
            texto={props.texto(valor)}
            marcada={props.seleccion.includes(valor)}
            alCambiar={(marcada) =>
              props.alCambiar(
                marcada ? [...props.seleccion, valor] : props.seleccion.filter((v) => v !== valor),
              )
            }
          />
        ))}
      </div>
    </Grupo>
  );
}

/** One end of the rent range. Sliding to that end removes the limit. */
function Deslizador(props: {
  texto: string;
  min: number;
  max: number;
  valor: number | null;
  extremo: number;
  alCambiar: (valor: number | null) => void;
}) {
  const actual = props.valor ?? props.extremo;
  return (
    <label class="block py-1">
      <span class="flex justify-between gap-2">
        <span>{props.texto}</span>
        <span class="font-semibold">{props.valor === null ? 'Sin límite' : formatEur(props.valor)}</span>
      </span>
      <input
        type="range"
        class="h-11 w-full"
        min={props.min}
        max={props.max}
        step={10}
        value={actual}
        aria-valuetext={props.valor === null ? 'Sin límite' : `${formatEur(props.valor)} al mes`}
        onInput={(e) => {
          const nuevo = Number(e.currentTarget.value);
          props.alCambiar(nuevo === props.extremo ? null : nuevo);
        }}
      />
    </label>
  );
}

export default function Buscador({ promociones }: { promociones: IndiceItem[] }) {
  const [filtros, setFiltros] = useState<Filtros>(SIN_FILTROS);
  const [montado, setMontado] = useState(false);
  const [abierto, setAbierto] = useState(false);

  // The URL is read after mounting so that the first render matches the server's.
  useEffect(() => {
    setFiltros(leerFiltros(window.location.search));
    setMontado(true);
  }, []);

  useEffect(() => {
    if (!montado) return;
    const consulta = escribirFiltros(filtros);
    const { pathname, hash } = window.location;
    window.history.replaceState(null, '', pathname + (consulta ? `?${consulta}` : '') + hash);
  }, [filtros, montado]);

  const opciones = useMemo(() => opcionesDisponibles(promociones), [promociones]);
  const nombres = useMemo(() => new Map(opciones.municipios.map((m) => [m.ine, m.nombre])), [opciones]);
  const { visibles, sinDato } = useMemo(
    () => aplicarFiltros(promociones, filtros, filtros.orden === 'cierre' ? hoyEnMadrid() : ''),
    [promociones, filtros],
  );

  const cambiar = (cambio: Partial<Filtros>) => setFiltros((previo) => ({ ...previo, ...cambio }));
  const limpiar = () => setFiltros((previo) => ({ ...SIN_FILTROS, orden: previo.orden }));
  const activos = contarFiltros(filtros);
  // Sorting by rent is only offered when there is some rent to sort by (or a shared URL asks for it).
  const hayRentas = promociones.some((p) => p.tipologias.some((t) => t.renta_mensual_eur !== null));
  const ordenes = Object.entries(ORDENES).filter(
    ([valor]) => valor !== 'renta' || hayRentas || filtros.orden === 'renta',
  );
  const total = promociones.length;
  const plural = (n: number) => (n === 1 ? 'promoción' : 'promociones');

  const sinFiltro = [
    !opciones.renta && 'renta',
    !opciones.garaje && 'garaje',
    !opciones.trastero && 'trastero',
  ].filter(Boolean) as string[];
  // A filter arriving by URL must stay visible even if the data cannot satisfy it.
  const conRenta = opciones.renta !== null;
  const rentaActiva = filtros.rentaMin !== null || filtros.rentaMax !== null;

  return (
    <div class="md:grid md:grid-cols-[17rem_1fr] md:items-start md:gap-6">
      <div class="solo-js mb-4 md:mb-0">
        <button
          type="button"
          class="boton-secundario w-full md:hidden"
          aria-expanded={abierto}
          aria-controls="filtros"
          onClick={() => setAbierto(!abierto)}
        >
          {abierto ? 'Ocultar filtros' : 'Mostrar filtros'}
          {activos > 0 && ` (${activos})`}
        </button>
        <form
          id="filtros"
          aria-label="Filtros"
          class={`tarjeta mt-3 space-y-3 md:mt-0 md:block ${abierto ? 'block' : 'hidden'}`}
          onSubmit={(e) => e.preventDefault()}
        >
          <Casilla
            texto="Solo con inscripción abierta"
            marcada={filtros.soloAbiertas}
            alCambiar={(soloAbiertas) => cambiar({ soloAbiertas })}
          />
          <Seleccion
            leyenda="Municipio"
            valores={opciones.municipios.map((m) => m.ine)}
            seleccion={filtros.municipios}
            texto={(ine) => nombres.get(ine) ?? ine}
            alCambiar={(municipios) => cambiar({ municipios })}
            conDesplazamiento
          />
          <Seleccion
            leyenda="Programa"
            valores={opciones.programas}
            seleccion={filtros.programas}
            texto={(v) => PROGRAMAS[v]}
            alCambiar={(programas) => cambiar({ programas })}
          />
          <Seleccion
            leyenda="Régimen"
            valores={opciones.regimenes}
            seleccion={filtros.regimenes}
            texto={(v) => REGIMENES[v]}
            alCambiar={(regimenes) => cambiar({ regimenes })}
          />
          <Seleccion
            leyenda="Estado"
            valores={opciones.estados}
            seleccion={filtros.estados}
            texto={(v) => ESTADOS[v]}
            alCambiar={(estados) => cambiar({ estados })}
          />
          {(conRenta || rentaActiva) && (
            <Grupo leyenda="Renta mensual">
              {opciones.renta ? (
                <>
                  <Deslizador
                    texto="Desde"
                    {...opciones.renta}
                    valor={filtros.rentaMin}
                    extremo={opciones.renta.min}
                    alCambiar={(rentaMin) =>
                      cambiar({
                        rentaMin,
                        rentaMax:
                          rentaMin !== null && filtros.rentaMax !== null
                            ? Math.max(rentaMin, filtros.rentaMax)
                            : filtros.rentaMax,
                      })
                    }
                  />
                  <Deslizador
                    texto="Hasta"
                    {...opciones.renta}
                    valor={filtros.rentaMax}
                    extremo={opciones.renta.max}
                    alCambiar={(rentaMax) =>
                      cambiar({
                        rentaMax,
                        rentaMin:
                          rentaMax !== null && filtros.rentaMin !== null
                            ? Math.min(rentaMax, filtros.rentaMin)
                            : filtros.rentaMin,
                      })
                    }
                  />
                </>
              ) : (
                <button
                  type="button"
                  class="boton-secundario w-full"
                  onClick={() => cambiar({ rentaMin: null, rentaMax: null })}
                >
                  Quitar filtro de renta
                </button>
              )}
            </Grupo>
          )}
          {(opciones.dormitorios.length > 0 || filtros.dormitorios !== null) && (
            <Grupo leyenda="Vivienda">
              <label class="block py-1">
                <span class="block">Dormitorios (mínimo)</span>
                <select
                  class={SELECTOR}
                  value={filtros.dormitorios ?? ''}
                  onChange={(e) =>
                    cambiar({ dormitorios: e.currentTarget.value ? Number(e.currentTarget.value) : null })
                  }
                >
                  <option value="">Cualquiera</option>
                  {opciones.dormitorios.map((n) => (
                    <option key={n} value={n}>
                      {n} o más
                    </option>
                  ))}
                </select>
              </label>
            </Grupo>
          )}
          {(opciones.garaje || filtros.garaje !== null) && (
            <label class="block">
              <span class="block font-semibold">Garaje</span>
              <select
                class={SELECTOR}
                value={filtros.garaje ?? ''}
                onChange={(e) => cambiar({ garaje: (e.currentTarget.value || null) as FiltroGaraje | null })}
              >
                <option value="">Indiferente</option>
                {Object.entries(FILTROS_GARAJE).map(([valor, texto]) => (
                  <option key={valor} value={valor}>
                    {texto}
                  </option>
                ))}
              </select>
            </label>
          )}
          {(opciones.trastero || filtros.trastero) && (
            <Casilla
              texto="Con trastero (incluido u opcional)"
              marcada={filtros.trastero}
              alCambiar={(trastero) => cambiar({ trastero })}
            />
          )}
          {sinFiltro.length > 0 && (
            <p class="text-sm text-slate-600">
              Aún no hay datos suficientes para filtrar por: {sinFiltro.join(', ')}.
            </p>
          )}
          <button type="button" class="boton-secundario w-full" onClick={limpiar} disabled={activos === 0}>
            Quitar filtros
          </button>
        </form>
      </div>

      <section aria-label="Resultados">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div role="status" aria-live="polite">
            <p class="font-semibold">
              {activos > 0 ? `${visibles.length} de ${total} ${plural(total)}` : `${total} ${plural(total)}`}
            </p>
            {sinDato > 0 && (
              <p class="text-sm text-slate-700">
                {sinDato === 1
                  ? '1 promoción oculta porque falta algún dato para saber si cumple.'
                  : `${sinDato} promociones ocultas porque falta algún dato para saber si cumplen.`}
              </p>
            )}
          </div>
          <label class="solo-js flex items-center gap-2">
            <span>Ordenar por</span>
            <select
              class="min-h-11 rounded-md border border-slate-500 bg-white px-2"
              value={filtros.orden}
              onChange={(e) => cambiar({ orden: e.currentTarget.value as Orden })}
            >
              {ordenes.map(([valor, texto]) => (
                <option key={valor} value={valor}>
                  {texto}
                </option>
              ))}
            </select>
          </label>
        </div>

        {visibles.length > 0 ? (
          <ul class="grid gap-3 sm:grid-cols-2">
            {visibles.map((promo) => (
              <li key={promo.id}>
                <TarjetaPromo promo={promo} />
              </li>
            ))}
          </ul>
        ) : (
          <p class="tarjeta">
            {total === 0
              ? 'Todavía no hay promociones publicadas.'
              : 'Ninguna promoción cumple los filtros elegidos.'}
          </p>
        )}
      </section>
    </div>
  );
}
