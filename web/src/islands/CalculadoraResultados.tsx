// Results of the calculator (ARCHITECTURE.md §6.3), grouped by verdict. Each group is rendered in
// batches and every breakdown sits in <details>: most promotions are still "posiblemente".
import { useState } from 'preact/hooks';
import BadgeEstado from '../components/BadgeEstado';
import type {
  EntradaCalculadora,
  EstadoRegla,
  IdRegla,
  ResultadoPromocion,
  Veredicto,
} from '../lib/contratos-calculadora';
import { etiquetaDormitorios } from '../lib/etiquetas';
import { formatEur } from '../lib/format';
import { ORIGENES } from '../lib/requisitos';
import { urlPromocion } from '../lib/rutas';

const POR_TANDA = 10;

const GRUPOS: Record<Veredicto, { titulo: string; explicacion: string; color: string; etiqueta: string }> = {
  elegible: {
    titulo: 'Elegible',
    explicacion: 'Cumples todo lo que se puede comprobar. Revisa las demás condiciones en cada una.',
    color: 'bg-green-100 text-green-900',
    etiqueta: 'Elegible',
  },
  posiblemente: {
    titulo: 'Posiblemente elegible',
    explicacion:
      'Nada te descarta con lo que sabemos, pero falta algún dato o se usa un valor general sin verificar.',
    color: 'bg-amber-100 text-amber-900',
    etiqueta: 'Posiblemente elegible',
  },
  no_elegible: {
    titulo: 'No elegible',
    explicacion: 'Al menos un requisito no se cumple. Se muestra el primero.',
    color: 'bg-red-100 text-red-900',
    etiqueta: 'No elegible',
  },
};
const VEREDICTOS = Object.keys(GRUPOS) as Veredicto[];

const REGLAS: Record<IdRegla, string> = {
  ingresos_max: 'Ingresos máximos',
  ingresos_min: 'Ingresos mínimos',
  tasa_esfuerzo: 'Esfuerzo de la renta',
  empadronamiento: 'Empadronamiento',
  edad: 'Edad',
  titularidad: 'Otra vivienda en propiedad',
  estado: 'Estado de la promoción',
};

const ESTADOS_REGLA: Record<EstadoRegla, { texto: string; color: string }> = {
  CUMPLE: { texto: 'Cumple', color: 'bg-green-100 text-green-900' },
  NO_CUMPLE: { texto: 'No cumple', color: 'bg-red-100 text-red-900' },
  DESCONOCIDO: { texto: 'Sin comprobar', color: 'bg-amber-100 text-amber-900' },
  INFORMATIVO: { texto: 'Informativo', color: 'bg-blue-100 text-blue-900' },
};

const SIN_VERIFICAR = 'valor general sin verificar';
const Insignia = () => <span class="etiqueta bg-amber-100 text-amber-900">{SIN_VERIFICAR}</span>;

const promociones = (n: number): string => `${n} ${n === 1 ? 'promoción' : 'promociones'}`;

function vivienda(dormitorios: number | null): string {
  if (dormitorios === null) return 'una vivienda (dormitorios no disponibles)';
  if (dormitorios === 0) return 'el estudio';
  return `la vivienda de ${etiquetaDormitorios(dormitorios)}`;
}

/** "Necesitas al menos X €/año…" for each dwelling type that matches the bedroom preference. */
function IngresosMinimos({ resultado, entrada }: { resultado: ResultadoPromocion; entrada: EntradaCalculadora }) {
  const minimo = entrada.dormitorios_min;
  const lineas = new Map<string, boolean>();
  for (const t of resultado.tipologias) {
    if (t.ingreso_minimo_anual === null) continue;
    if (minimo !== null && t.dormitorios !== null && t.dormitorios < minimo) continue;
    const texto = `Necesitas al menos ${formatEur(t.ingreso_minimo_anual)}/año para ${vivienda(t.dormitorios)}`;
    lineas.set(texto, t.estado === 'CUMPLE');
  }
  if (lineas.size === 0) return null;
  return (
    <ul class="space-y-1 text-sm">
      {[...lineas].map(([texto, llega]) => (
        <li key={texto}>
          {texto}: <strong>{llega ? 'llegas' : 'no llegas'}</strong>
          {entrada.ingresos_estimados && ' (con ingresos estimados)'}.
        </li>
      ))}
    </ul>
  );
}

function Desglose({ resultado }: { resultado: ResultadoPromocion }) {
  const { promocion, avisos } = resultado;
  const { condiciones } = promocion.requisitos;
  return (
    <details class="border-t border-slate-200">
      <summary class="min-h-11 cursor-pointer py-2.5 font-semibold text-blue-900">
        Desglose de requisitos<span class="sr-only"> de {promocion.nombre}</span>
      </summary>
      <ul class="divide-y divide-slate-200">
        {resultado.reglas.map((regla) => (
          <li key={regla.id} class="py-2">
            <p class="flex flex-wrap items-center gap-2">
              <span class={`etiqueta ${ESTADOS_REGLA[regla.estado].color}`}>
                {ESTADOS_REGLA[regla.estado].texto}
              </span>
              <strong>{REGLAS[regla.id]}</strong>
            </p>
            <p class="mt-1">{regla.explicacion}</p>
            {(regla.origen !== null || regla.sin_verificar) && (
              <p class="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-700">
                {regla.origen !== null && <span>Origen: {ORIGENES[regla.origen]}</span>}
                {regla.sin_verificar && <Insignia />}
              </p>
            )}
          </li>
        ))}
      </ul>
      {avisos.length > 0 && (
        <>
          <h5 class="mt-3 font-bold">Avisos del cálculo</h5>
          <ul class="mt-1 list-disc space-y-1 pl-5">
            {avisos.map((aviso) => (
              <li key={aviso}>{aviso}</li>
            ))}
          </ul>
        </>
      )}
      <h5 class="mt-3 font-bold">También debes cumplir</h5>
      {condiciones.length === 0 ? (
        <p class="mt-1 text-sm">No constan otras condiciones: consulta las bases.</p>
      ) : (
        <ul class="mt-1 list-disc space-y-2 pl-5">
          {condiciones.map((c) => (
            <li key={c.texto}>
              {c.texto}
              <span class="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-700">
                <span>Origen: {ORIGENES[c.origen]}</span>
                {c.sin_verificar && <Insignia />}
              </span>
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

/** Why it is only "posiblemente": the rules still to check, or the unverified values. */
function Pendiente({ resultado }: { resultado: ResultadoPromocion }) {
  const sinComprobar = resultado.reglas.filter((r) => r.estado === 'DESCONOCIDO').map((r) => REGLAS[r.id]);
  if (sinComprobar.length > 0) {
    return (
      <p class="text-sm">
        <strong>Sin comprobar:</strong> {sinComprobar.join(', ').toLowerCase()}.
      </p>
    );
  }
  return <p class="text-sm">Cumples lo comprobado, pero depende de algún valor general sin verificar.</p>;
}

function Tarjeta(props: {
  resultado: ResultadoPromocion;
  entrada: EntradaCalculadora;
  /** Warnings only this promotion has; shared ones are summarised above the lists. */
  avisos: string[];
}) {
  const { resultado, entrada } = props;
  const { promocion, veredicto } = resultado;
  const primeraNoCumple = resultado.reglas.find((r) => r.estado === 'NO_CUMPLE');
  // The official calculator weights income by household size; without that data we cannot.
  const sinCoeficiente =
    primeraNoCumple?.id === 'ingresos_max' && promocion.requisitos.coeficientes_ponderacion.valor === null;

  return (
    <article class="tarjeta space-y-2 break-words">
      <div class="flex flex-wrap gap-2">
        <span class={`etiqueta ${GRUPOS[veredicto].color}`}>{GRUPOS[veredicto].etiqueta}</span>
        <BadgeEstado estado={promocion.estado} />
        {!promocion.activa_en_fuente && (
          <span class="etiqueta bg-red-100 text-red-900">Ya no aparece en la fuente</span>
        )}
        {entrada.ingresos_estimados && (
          <span class="etiqueta border border-amber-700 bg-amber-50 text-amber-950">
            Aproximación: ingresos estimados
          </span>
        )}
      </div>
      <h4 class="text-lg font-bold">
        <a class="enlace inline-block py-2" href={urlPromocion(promocion.id)}>
          {promocion.nombre}
        </a>
      </h4>
      <p class="text-sm text-slate-700">
        {promocion.municipio} · {promocion.operador}
      </p>
      {veredicto === 'no_elegible' && resultado.motivo_no_elegible && (
        <p>
          <strong>Motivo:</strong> {resultado.motivo_no_elegible}
        </p>
      )}
      {sinCoeficiente && (
        <p class="text-sm">
          No se ha aplicado ningún coeficiente por número de miembros. Si te pasas por poco, compruébalo en la
          calculadora oficial.
        </p>
      )}
      {veredicto === 'posiblemente' && <Pendiente resultado={resultado} />}
      <IngresosMinimos resultado={resultado} entrada={entrada} />
      {props.avisos.map((aviso) => (
        <p key={aviso} class="rounded-md bg-amber-50 p-2 text-sm text-amber-950">
          {aviso}
        </p>
      ))}
      <Desglose resultado={resultado} />
    </article>
  );
}

function Grupo(props: {
  veredicto: Veredicto;
  resultados: ResultadoPromocion[];
  entrada: EntradaCalculadora;
  avisosRepetidos: Map<string, number>;
}) {
  const [visibles, setVisibles] = useState(POR_TANDA);
  const { resultados, veredicto } = props;
  if (resultados.length === 0) return null;
  const resto = resultados.length - visibles;
  const id = `grupo-${veredicto}`;
  return (
    <section aria-labelledby={id} class="space-y-3">
      <div>
        <h3 id={id} class="text-xl font-bold">
          {GRUPOS[veredicto].titulo} ({resultados.length})
        </h3>
        <p class="text-sm text-slate-700">{GRUPOS[veredicto].explicacion}</p>
      </div>
      <ul class="space-y-3">
        {resultados.slice(0, visibles).map((r) => (
          <li key={r.promocion.id}>
            <Tarjeta
              resultado={r}
              entrada={props.entrada}
              avisos={r.avisos.filter((a) => !props.avisosRepetidos.has(a))}
            />
          </li>
        ))}
      </ul>
      {resto > 0 && (
        <button type="button" class="boton-secundario w-full" onClick={() => setVisibles(visibles + POR_TANDA)}>
          Mostrar {Math.min(resto, POR_TANDA)} más de «{GRUPOS[veredicto].titulo}» (quedan {resto})
        </button>
      )}
    </section>
  );
}

function recuento(resultados: ResultadoPromocion[]): string {
  const cuantas = (v: Veredicto) => resultados.filter((r) => r.veredicto === v).length;
  const si = cuantas('elegible');
  return (
    `${promociones(resultados.length)}: ${si} ${si === 1 ? 'elegible' : 'elegibles'}, ` +
    `${cuantas('posiblemente')} posiblemente y ${cuantas('no_elegible')} no.`
  );
}

/** Warnings shared by several promotions, with how many: said once instead of on every card. */
function avisosRepetidos(resultados: ResultadoPromocion[]): Map<string, number> {
  const cuenta = new Map<string, number>();
  for (const r of resultados) {
    for (const aviso of r.avisos) cuenta.set(aviso, (cuenta.get(aviso) ?? 0) + 1);
  }
  return new Map([...cuenta].filter(([, n]) => n > 1));
}

/** Which requirements are most often impossible to check, most frequent first. */
function loQueFalta(resultados: ResultadoPromocion[]): [IdRegla, number][] {
  const cuenta = new Map<IdRegla, number>();
  for (const r of resultados) {
    if (r.veredicto !== 'posiblemente') continue;
    for (const regla of r.reglas) {
      if (regla.estado === 'DESCONOCIDO') cuenta.set(regla.id, (cuenta.get(regla.id) ?? 0) + 1);
    }
  }
  return [...cuenta].sort((a, b) => b[1] - a[1]);
}

export interface Calculo {
  /** Increases with every calculation: used to start the lists from the top again. */
  numero: number;
  entrada: EntradaCalculadora;
  resultados: ResultadoPromocion[];
  /** Promotions left out of `resultados`. */
  finalizadasOcultas: number;
  ocultasPorDormitorios: number;
}

export default function CalculadoraResultados(props: {
  calculo: Calculo | null;
  /** The form changed after this calculation. */
  desfasado: boolean;
  mostrarFinalizadas: boolean;
  alMostrarFinalizadas: (mostrar: boolean) => void;
}) {
  const { calculo } = props;
  const resultados = calculo?.resultados ?? [];
  const repetidos = avisosRepetidos(resultados);
  const falta = loQueFalta(resultados);

  return (
    <section aria-label="Resultados" class="space-y-4">
      {calculo && (
        <h2 id="calc-resultados" tabIndex={-1} class="scroll-mt-4 text-2xl font-bold">
          Resultados
        </h2>
      )}
      {/* The live region exists before it has content, so that screen readers announce it. */}
      <div role="status">
        {calculo && (
          <p class="font-semibold">
            {recuento(resultados)}
            {calculo.entrada.ingresos_estimados && ' Aproximación con ingresos estimados.'}
          </p>
        )}
        {calculo && props.desfasado && (
          <p class="mt-2 rounded-md border border-amber-700 bg-amber-50 p-3 text-amber-950">
            Has cambiado datos del formulario. Pulsa «Ver resultados» para actualizar.
          </p>
        )}
      </div>

      {calculo && (
        <>
          {calculo.entrada.ingresos_estimados && (
            <p class="rounded-md border border-amber-700 bg-amber-50 p-3 text-amber-950">
              <strong>Aproximación.</strong> Se ha usado una base imponible estimada de{' '}
              {formatEur(calculo.entrada.ingresos_anuales)} a partir del bruto, con una sola deducción de 2.000
              €. Los resultados pueden cambiar con las cifras de la declaración de la renta.
            </p>
          )}
          <div class="space-y-2 rounded-md border border-blue-300 bg-blue-50 p-3 text-sm">
            <p>
              <strong>Es una orientación, no una resolución.</strong> No decide si puedes optar a una vivienda:
              la convocatoria oficial prevalece siempre.
            </p>
            <p>
              El esfuerzo de la renta se calcula con la cifra{' '}
              {calculo.entrada.ingresos_estimados ? 'estimada' : 'que has escrito'}. Algunas convocatorias (por
              ejemplo, las preguntas frecuentes del Plan Vive) calculan el 35 % sobre los ingresos{' '}
              <strong>netos</strong> y la renta total.
            </p>
          </div>

          {[...repetidos].map(([aviso, n]) => (
            <p key={aviso} class="rounded-md bg-amber-50 p-3 text-sm text-amber-950">
              {aviso} <span class="whitespace-nowrap">(Afecta a {promociones(n)}.)</span>
            </p>
          ))}

          {falta.length > 0 && (
            <div class="tarjeta">
              <p class="font-semibold">Qué falta por comprobar en las «posiblemente»</p>
              <ul class="mt-1 list-disc pl-5 text-sm">
                {falta.map(([id, n]) => (
                  <li key={id}>
                    {REGLAS[id]}: en {promociones(n)}
                  </li>
                ))}
              </ul>
              <p class="mt-1 text-sm text-slate-700">
                Suele ser porque la fuente no publica el dato o porque has dejado una casilla en blanco.
              </p>
            </div>
          )}

          <div>
            <label class="flex min-h-11 cursor-pointer items-center gap-3">
              <input
                type="checkbox"
                class="size-5 shrink-0"
                autocomplete="off"
                checked={props.mostrarFinalizadas}
                onChange={(e) => props.alMostrarFinalizadas(e.currentTarget.checked)}
              />
              <span>
                Mostrar finalizadas
                {calculo.finalizadasOcultas > 0 && ` (${calculo.finalizadasOcultas} ocultas)`}
              </span>
            </label>
            {calculo.ocultasPorDormitorios > 0 && (
              <p class="text-sm text-slate-700">
                No aparecen {promociones(calculo.ocultasPorDormitorios)} por tu preferencia de dormitorios.
              </p>
            )}
          </div>

          {resultados.length === 0 && <p class="tarjeta">No hay ninguna promoción que mostrar.</p>}
          {VEREDICTOS.map((veredicto) => (
            <Grupo
              key={`${calculo.numero}-${veredicto}`}
              veredicto={veredicto}
              resultados={resultados.filter((r) => r.veredicto === veredicto)}
              entrada={calculo.entrada}
              avisosRepetidos={repetidos}
            />
          ))}
        </>
      )}
    </section>
  );
}
