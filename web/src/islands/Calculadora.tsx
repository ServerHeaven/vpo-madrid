// Calculator island (ARCHITECTURE.md §6). Privacy: what the person types lives only in the memory
// of this component. No storage, no URL or history writes and no requests: all data comes as props.
import { useEffect, useMemo, useState } from 'preact/hooks';
import type { DatosCalculadora, EntradaCalculadora } from '../lib/contratos-calculadora';
import { evaluarTodas } from '../lib/eligibility';
import { CAMPOS_VACIOS, leerCampos, type Campos, type Errores } from './CalculadoraEntrada';
import CalculadoraFormulario, { idCampo } from './CalculadoraFormulario';
import CalculadoraResultados, { type Calculo } from './CalculadoraResultados';

const anioEnMadrid = (): number =>
  Number(new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Madrid', year: 'numeric' }).format(new Date()));

export default function Calculadora({ datos }: { datos: DatosCalculadora }) {
  const [campos, setCampos] = useState<Campos>(CAMPOS_VACIOS);
  // null until mounted: the current year is the visitor's, not the build's.
  const [anioActual, setAnioActual] = useState<number | null>(null);
  // Errors are only shown after trying to calculate.
  const [intentado, setIntentado] = useState(false);
  const [pedido, setPedido] = useState<{ numero: number; entrada: EntradaCalculadora } | null>(null);
  const [mostrarFinalizadas, setMostrarFinalizadas] = useState(false);

  useEffect(() => {
    const actual = anioEnMadrid();
    setAnioActual(actual);
    setCampos((previos) => ({ ...previos, ejercicio: String(actual - 1) }));
  }, []);

  const anios = useMemo(() => {
    if (anioActual === null) return [];
    const primero = Math.min(anioActual - 1, ...datos.iprem.map((i) => i.anio));
    return Array.from({ length: anioActual - primero + 1 }, (_, i) => anioActual - i);
  }, [anioActual, datos.iprem]);

  const lectura = useMemo(() => leerCampos(campos, datos.municipios), [campos, datos.municipios]);
  const errores: Errores = intentado ? (lectura.errores ?? {}) : {};

  const calculo = useMemo((): Calculo | null => {
    if (!pedido) return null;
    const resultados = evaluarTodas(datos.promociones, pedido.entrada, datos.iprem, { mostrarFinalizadas });
    const finalizadas = datos.promociones.filter((p) => p.estado === 'finalizada').length;
    const finalizadasOcultas = mostrarFinalizadas ? 0 : finalizadas;
    return {
      ...pedido,
      resultados,
      finalizadasOcultas,
      ocultasPorDormitorios: datos.promociones.length - finalizadasOcultas - resultados.length,
    };
  }, [pedido, mostrarFinalizadas, datos]);

  const desfasado = pedido !== null && JSON.stringify(lectura.entrada) !== JSON.stringify(pedido.entrada);

  // On a phone the results are far below the button: take the reader there.
  useEffect(() => {
    if (pedido) document.getElementById('calc-resultados')?.focus();
  }, [pedido]);

  function calcular() {
    setIntentado(true);
    if (lectura.entrada) {
      setPedido((previo) => ({ numero: (previo?.numero ?? 0) + 1, entrada: lectura.entrada }));
      return;
    }
    const primero = (Object.keys(CAMPOS_VACIOS) as (keyof Campos)[]).find((c) => lectura.errores[c]);
    if (primero) document.getElementById(idCampo(primero))?.focus();
  }

  function borrar() {
    setCampos({ ...CAMPOS_VACIOS, ejercicio: anioActual === null ? '' : String(anioActual - 1) });
    setIntentado(false);
    setPedido(null);
    setMostrarFinalizadas(false);
  }

  return (
    <div class="max-w-3xl space-y-6">
      <CalculadoraFormulario
        campos={campos}
        errores={errores}
        activo={anioActual !== null}
        anios={anios}
        municipios={datos.municipios}
        cambiar={(cambio) => setCampos((previos) => ({ ...previos, ...cambio }))}
        alCalcular={calcular}
        alBorrar={borrar}
      />
      <CalculadoraResultados
        calculo={calculo}
        desfasado={desfasado}
        mostrarFinalizadas={mostrarFinalizadas}
        alMostrarFinalizadas={setMostrarFinalizadas}
      />
    </div>
  );
}
