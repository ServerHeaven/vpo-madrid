// The calculator form. Privacy: nothing here can submit natively (method="dialog" outside a dialog
// does nothing, no control has a `name`, and everything stays disabled until the island is hydrated).
import type { ComponentChildren } from 'preact';
import type { Municipio } from '../lib/contratos-calculadora';
import { estimarBaseImponible } from '../lib/eligibility';
import { formatEur } from '../lib/format';
import { leerNumero, type Campos, type Errores } from './CalculadoraEntrada';

/** Official sources, checked on 2026-11-27. */
const MANUAL_INGRESOS =
  'https://www.comunidad.madrid/docs/2026-07/viv_prot_manual_calculadora_irpf_2025.pdf';
const PAGINA_INGRESOS = 'https://www.comunidad.madrid/vivienda/vivienda-protegida-nueva-construccion';

const ENTRADA =
  'min-h-11 w-full min-w-0 rounded-md border border-slate-500 bg-white px-3 aria-[invalid=true]:border-red-700 disabled:bg-slate-100';
const CASILLA = 'flex min-h-11 cursor-pointer items-center gap-3';
const ENLACE_AYUDA = 'enlace inline-flex min-h-11 items-center';

export const idCampo = (campo: keyof Campos): string => `calc-${campo}`;
const LISTA_MUNICIPIOS = 'calc-municipios';

type Cambiar = (cambio: Partial<Campos>) => void;

/** Attributes that tie a control to its help and error texts. */
function describir(campo: keyof Campos, errores: Errores, conAyuda = false) {
  const ids = [conAyuda && `${idCampo(campo)}-ayuda`, errores[campo] && `${idCampo(campo)}-error`]
    .filter(Boolean)
    .join(' ');
  return {
    id: idCampo(campo),
    'aria-invalid': errores[campo] ? true : undefined,
    'aria-describedby': ids || undefined,
  };
}

function Campo(props: {
  campo: keyof Campos;
  etiqueta: string;
  errores: Errores;
  ayuda?: ComponentChildren;
  children: ComponentChildren;
}) {
  const error = props.errores[props.campo];
  return (
    <div class="min-w-0">
      <label class="mb-1 block font-semibold" for={idCampo(props.campo)}>
        {props.etiqueta}
      </label>
      {props.children}
      {error && (
        <p id={`${idCampo(props.campo)}-error`} class="mt-1 text-sm font-semibold text-red-800">
          {error}
        </p>
      )}
      {props.ayuda && (
        <div id={`${idCampo(props.campo)}-ayuda`} class="mt-1 text-sm text-slate-700">
          {props.ayuda}
        </div>
      )}
    </div>
  );
}

function Lugar(props: {
  leyenda: string;
  campo: 'empadronamiento' | 'trabajo';
  campoAnios: 'aniosEmpadronamiento' | 'aniosTrabajo';
  etiquetaMunicipio: string;
  etiquetaAnios: string;
  campos: Campos;
  errores: Errores;
  cambiar: Cambiar;
}) {
  const { campos, errores, campo, campoAnios, cambiar } = props;
  const campoFuera = campo === 'empadronamiento' ? 'empadronamientoFuera' : 'trabajoFuera';
  const fuera = campos[campoFuera];
  return (
    <fieldset class="border-t border-slate-200 pt-3">
      <legend class="pr-2 text-lg font-bold">{props.leyenda}</legend>
      <div class="grid gap-3 sm:grid-cols-[2fr_1fr] sm:items-start">
        <Campo campo={campo} etiqueta={props.etiquetaMunicipio} errores={errores}>
          <input
            {...describir(campo, errores)}
            class={ENTRADA}
            type="text"
            list={LISTA_MUNICIPIOS}
            autocomplete="off"
            placeholder="Empieza a escribir y elige"
            disabled={fuera}
            value={fuera ? '' : campos[campo]}
            onInput={(e) => cambiar({ [campo]: e.currentTarget.value })}
          />
        </Campo>
        <Campo campo={campoAnios} etiqueta={props.etiquetaAnios} errores={errores}>
          <input
            {...describir(campoAnios, errores)}
            class={ENTRADA}
            type="text"
            inputMode="decimal"
            autocomplete="off"
            disabled={fuera}
            value={fuera ? '' : campos[campoAnios]}
            onInput={(e) => cambiar({ [campoAnios]: e.currentTarget.value })}
          />
        </Campo>
      </div>
      <label class={CASILLA}>
        <input
          type="checkbox"
          class="size-5 shrink-0"
          autocomplete="off"
          checked={fuera}
          onChange={(e) => cambiar({ [campoFuera]: e.currentTarget.checked })}
        />
        <span>Fuera de la Comunidad de Madrid</span>
      </label>
    </fieldset>
  );
}

function AyudaIngresos({ soloBruto, ingresos }: { soloBruto: boolean; ingresos: string }) {
  const cantidad = leerNumero(ingresos);
  if (soloBruto) {
    return (
      <p>
        Suma el salario bruto anual de todas las personas de la unidad de convivencia.
        {cantidad !== null && (
          <>
            {' '}
            Base imponible estimada: <strong>{formatEur(estimarBaseImponible(cantidad))}</strong>{' '}
            (aproximación).
          </>
        )}
      </p>
    );
  }
  return (
    <>
      <p>
        En la Comunidad de Madrid se usa normalmente la <strong>suma de la base imponible general y del
        ahorro</strong> de la última declaración de la renta de todos los miembros, no el salario bruto.
        {cantidad !== null && (
          <>
            {' '}
            Se ha entendido: <strong>{formatEur(cantidad)}</strong> al año.
          </>
        )}
      </p>
      <p class="flex flex-wrap gap-x-4">
        <a class={ENLACE_AYUDA} href={MANUAL_INGRESOS}>
          Manual oficial de ingresos (PDF)
        </a>
        <a class={ENLACE_AYUDA} href={PAGINA_INGRESOS}>
          Calculadora oficial de la Comunidad
        </a>
      </p>
    </>
  );
}

export default function CalculadoraFormulario(props: {
  campos: Campos;
  errores: Errores;
  /** false until the island is hydrated. */
  activo: boolean;
  anios: number[];
  municipios: Municipio[];
  cambiar: Cambiar;
  alCalcular: () => void;
  alBorrar: () => void;
}) {
  const { campos, errores, cambiar } = props;
  const numErrores = Object.keys(errores).length;

  return (
    <form
      method="dialog"
      novalidate
      autocomplete="off"
      aria-label="Tus datos"
      class="tarjeta"
      onSubmit={(e) => {
        e.preventDefault();
        props.alCalcular();
      }}
    >
      <fieldset disabled={!props.activo} class="min-w-0 space-y-4">
        <legend class="sr-only">Datos para calcular los requisitos</legend>
        <p class="text-sm text-slate-700">
          Solo son obligatorios los ingresos y el número de personas. Lo que dejes en blanco aparecerá como
          requisito sin comprobar.
        </p>

        <fieldset class="space-y-3">
          <legend class="mb-2 text-lg font-bold">Ingresos y unidad de convivencia</legend>
          <label class={CASILLA}>
            <input
              type="checkbox"
              role="switch"
              class="size-5 shrink-0"
              autocomplete="off"
              checked={campos.soloBruto}
              onChange={(e) => cambiar({ soloBruto: e.currentTarget.checked })}
            />
            <span>Solo sé mi bruto anual</span>
          </label>
          {campos.soloBruto && (
            <p class="rounded-md border border-amber-700 bg-amber-50 p-3 text-sm text-amber-950">
              <strong>Aproximación.</strong> Calculamos la base imponible como bruto − cotizaciones a la
              Seguridad Social (≈ 6,35 %) − 2.000 € de gastos deducibles. Se aplica{' '}
              <strong>una sola deducción de 2.000 €</strong>, aunque haya varias personas con sueldo. Para un
              resultado fiable, usa las cifras de la declaración de la renta.
            </p>
          )}
          <Campo
            campo="ingresos"
            etiqueta={
              campos.soloBruto
                ? 'Ingresos brutos anuales de la unidad de convivencia (€) · obligatorio'
                : 'Ingresos de la unidad de convivencia (IRPF), en euros al año · obligatorio'
            }
            errores={errores}
            ayuda={<AyudaIngresos soloBruto={campos.soloBruto} ingresos={campos.ingresos} />}
          >
            <input
              {...describir('ingresos', errores, true)}
              class={ENTRADA}
              type="text"
              inputMode="decimal"
              autocomplete="off"
              required
              value={campos.ingresos}
              onInput={(e) => cambiar({ ingresos: e.currentTarget.value })}
            />
          </Campo>
          <div class="grid gap-3 sm:grid-cols-2 sm:items-start">
            <Campo campo="miembros" etiqueta="Personas en la unidad · obligatorio" errores={errores}>
              <select
                {...describir('miembros', errores)}
                class={ENTRADA}
                autocomplete="off"
                required
                value={campos.miembros}
                onChange={(e) => cambiar({ miembros: e.currentTarget.value })}
              >
                <option value="">Elige</option>
                {Array.from({ length: 10 }, (_, i) => String(i + 1)).map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </Campo>
            <Campo
              campo="ejercicio"
              etiqueta="Año de los ingresos"
              errores={errores}
              ayuda={<p>Normalmente, el de la última declaración cuyo plazo ya ha terminado.</p>}
            >
              <select
                {...describir('ejercicio', errores, true)}
                class={ENTRADA}
                autocomplete="off"
                value={campos.ejercicio}
                onChange={(e) => cambiar({ ejercicio: e.currentTarget.value })}
              >
                {props.anios.map((anio) => (
                  <option key={anio} value={String(anio)}>
                    {anio}
                  </option>
                ))}
              </select>
            </Campo>
          </div>
        </fieldset>

        <Lugar
          leyenda="Dónde estás empadronado"
          campo="empadronamiento"
          campoAnios="aniosEmpadronamiento"
          etiquetaMunicipio="Municipio de empadronamiento"
          etiquetaAnios="Años empadronado"
          campos={campos}
          errores={errores}
          cambiar={cambiar}
        />
        <Lugar
          leyenda="Dónde trabajas (opcional)"
          campo="trabajo"
          campoAnios="aniosTrabajo"
          etiquetaMunicipio="Municipio de trabajo"
          etiquetaAnios="Años trabajando allí"
          campos={campos}
          errores={errores}
          cambiar={cambiar}
        />
        <datalist id={LISTA_MUNICIPIOS}>
          {props.municipios.map((m) => (
            <option key={m.ine} value={m.nombre} />
          ))}
        </datalist>

        <fieldset class="border-t border-slate-200 pt-3">
          <legend class="pr-2 text-lg font-bold">Sobre ti y la vivienda</legend>
          <div class="grid gap-3 sm:grid-cols-3 sm:items-start">
            <Campo campo="edad" etiqueta="Edad del solicitante" errores={errores}>
              <input
                {...describir('edad', errores)}
                class={ENTRADA}
                type="text"
                inputMode="numeric"
                autocomplete="off"
                value={campos.edad}
                onInput={(e) => cambiar({ edad: e.currentTarget.value })}
              />
            </Campo>
            <Campo campo="titular" etiqueta="¿Tienes otra vivienda?" errores={errores}>
              <select
                {...describir('titular', errores)}
                class={ENTRADA}
                autocomplete="off"
                value={campos.titular}
                onChange={(e) => cambiar({ titular: e.currentTarget.value as Campos['titular'] })}
              >
                <option value="">No lo indico</option>
                <option value="no">No</option>
                <option value="si">Sí</option>
              </select>
            </Campo>
            <Campo campo="dormitorios" etiqueta="Dormitorios (mínimo)" errores={errores}>
              <select
                {...describir('dormitorios', errores)}
                class={ENTRADA}
                autocomplete="off"
                value={campos.dormitorios}
                onChange={(e) => cambiar({ dormitorios: e.currentTarget.value })}
              >
                <option value="">Cualquiera</option>
                {['1', '2', '3', '4'].map((n) => (
                  <option key={n} value={n}>
                    {n} o más
                  </option>
                ))}
              </select>
            </Campo>
          </div>
        </fieldset>

        {numErrores > 0 && (
          <p role="alert" class="font-semibold text-red-800">
            {numErrores === 1
              ? 'Hay un dato que revisar antes de calcular.'
              : `Hay ${numErrores} datos que revisar antes de calcular.`}
          </p>
        )}
        <div class="flex flex-wrap gap-3">
          <button type="submit" class="boton disabled:opacity-60" disabled={!props.activo}>
            Ver resultados
          </button>
          <button type="button" class="boton-secundario" onClick={props.alBorrar}>
            Borrar datos
          </button>
        </div>
      </fieldset>
    </form>
  );
}
