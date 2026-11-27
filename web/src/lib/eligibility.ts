// Eligibility engine (ARCHITECTURE.md §6.2-6.3). Pure: no DOM, no clock, no network, no storage.
// Rule: whatever cannot be established is DESCONOCIDO, never a guess.
import { FUERA_DE_LA_COMUNIDAD } from './contratos-calculadora';
import type {
  EntradaCalculadora,
  EstadoRegla,
  EstimarBaseImponible,
  EvaluarPromocion,
  EvaluarTodas,
  IdRegla,
  IpremAnual,
  IpremAplicable,
  IpremAplicado,
  Parametro,
  PromocionCalculadora,
  ResultadoPromocion,
  ResultadoRegla,
  ResultadoTipologia,
  Veredicto,
} from './contratos-calculadora';
import type { EstadoPromocion } from './contratos';
import { formatEur, formatNumero } from './format';
import { textoEdad } from './requisitos';

const COTIZACION_SEGURIDAD_SOCIAL = 0.0635;
const GASTOS_DEDUCIBLES_EUR = 2000;
const PAGAS_POR_DEFECTO = 14;
/** Absorbs floating point noise only: far below one cent, far above the error of these figures. */
const MARGEN = 1e-6;

/** A usable figure typed by the person, or null. */
const dato = (n: number | null): number | null => (n !== null && Number.isFinite(n) && n >= 0 ? n : null);

const positivo = (n: number | null): number | null => (n !== null && Number.isFinite(n) && n > 0 ? n : null);

export const estimarBaseImponible: EstimarBaseImponible = (brutoAnual) => {
  const base = brutoAnual * (1 - COTIZACION_SEGURIDAD_SOCIAL) - GASTOS_DEDUCIBLES_EUR;
  return Math.max(0, Math.round(base * 100) / 100);
};

export const ipremAplicable: IpremAplicable = (tabla, ejercicio, pagas) => {
  const exacto = tabla.find((f) => f.anio === ejercicio);
  const fila = exacto ?? [...tabla].sort((a, b) => b.anio - a.anio)[0];
  if (!fila) throw new Error('La tabla del IPREM está vacía');
  return {
    importe: pagas === 12 ? fila.anual_12 : fila.anual_14,
    anio: fila.anio,
    pagas,
    sustituido: !exacto,
  };
};

function resultado<T>(
  id: IdRegla,
  estado: EstadoRegla,
  explicacion: string,
  parametro: Parametro<T> | null,
  sinVerificar = parametro?.sin_verificar ?? false,
): ResultadoRegla {
  return { id, estado, explicacion, origen: parametro?.origen ?? 'desconocido', sin_verificar: sinVerificar };
}

// ---------------------------------------------------------------- R1 and R2: income limits

type Lado = 'max' | 'min';

interface Limite {
  parametro: Parametro<unknown> | null;
  /** Times the IPREM; null when unknown or not demanded. */
  veces: number | null;
}

function limiteDe(promocion: PromocionCalculadora, miembros: number, lado: Lado): Limite {
  const { requisitos } = promocion;
  const tabla = requisitos.ingresos_por_miembros;
  // A table by household size prevails over the flat limits.
  if (tabla) {
    const filas = (tabla.valor ?? []).filter(
      (f) => f.miembros_desde <= miembros && miembros <= (f.miembros_hasta ?? Infinity),
    );
    // Overlapping rows that disagree are a conflict, hence unknown.
    const valores = new Set(filas.map((f) => (lado === 'max' ? f.max_iprem : f.min_iprem)));
    const [unico] = valores;
    return { parametro: tabla, veces: valores.size === 1 ? dato(unico ?? null) : null };
  }
  const parametro = lado === 'max' ? requisitos.ingresos_max_iprem : requisitos.ingresos_min_iprem;
  return { parametro, veces: dato(parametro?.valor ?? null) };
}

interface IngresosPonderados {
  importe: number;
  /** Applied factor; null when the programme does not weigh the income. */
  coeficiente: number | null;
}

/** null when coefficients exist but none covers this household size. */
function ponderar(promocion: PromocionCalculadora, ingresos: number, miembros: number): IngresosPonderados | null {
  const tabla = promocion.requisitos.coeficientes_ponderacion.valor;
  if (tabla === null) return { importe: ingresos, coeficiente: null };
  const coeficiente = positivo(tabla[String(miembros)] ?? null);
  return coeficiente === null ? null : { importe: ingresos * coeficiente, coeficiente };
}

interface ContextoIprem {
  /** null until an income limit is actually compared, and when the table is empty. */
  iprem: IpremAplicado | null;
}

function reglaIngresos(
  lado: Lado,
  promocion: PromocionCalculadora,
  entrada: EntradaCalculadora,
  tabla: IpremAnual[],
  usado: ContextoIprem,
): ResultadoRegla {
  const id: IdRegla = lado === 'max' ? 'ingresos_max' : 'ingresos_min';
  const nombre = lado === 'max' ? 'máximo' : 'mínimo';
  const { requisitos } = promocion;
  const { parametro, veces } = limiteDe(promocion, entrada.miembros, lado);

  if (parametro?.valor === null && parametro.origen === 'no_exigido') {
    return resultado(id, 'CUMPLE', `Las bases no exigen un ${nombre} de ingresos.`, parametro);
  }
  if (veces === null) {
    const para = requisitos.ingresos_por_miembros ? ` para ${entrada.miembros} miembros` : '';
    return resultado(
      id,
      'DESCONOCIDO',
      `No consta el ${nombre} de ingresos${para}: consulta las bases.`,
      parametro,
    );
  }
  const ingresos = dato(entrada.ingresos_anuales);
  if (ingresos === null) {
    return resultado(id, 'DESCONOCIDO', `Indica los ingresos para comprobar el ${nombre}.`, parametro);
  }
  const ponderados = ponderar(promocion, ingresos, entrada.miembros);
  if (ponderados === null) {
    return resultado(
      id,
      'DESCONOCIDO',
      `El programa pondera los ingresos según el tamaño del hogar y no consta el coeficiente para ${entrada.miembros} miembros.`,
      parametro,
    );
  }
  if (tabla.length === 0) {
    return resultado(id, 'DESCONOCIDO', `No hay datos del IPREM para comprobar el ${nombre} de ingresos.`, parametro);
  }

  const iprem = ipremAplicable(
    tabla,
    requisitos.iprem_ejercicio.valor ?? entrada.ejercicio,
    requisitos.iprem_pagas.valor ?? PAGAS_POR_DEFECTO,
  );
  usado.iprem = iprem;

  const limite = veces * iprem.importe;
  const cumple =
    lado === 'max' ? ponderados.importe <= limite + MARGEN : ponderados.importe >= limite - MARGEN;
  const sinVerificar =
    (parametro?.sin_verificar ?? false) ||
    requisitos.iprem_pagas.sin_verificar ||
    requisitos.iprem_ejercicio.sin_verificar ||
    (ponderados.coeficiente !== null && requisitos.coeficientes_ponderacion.sin_verificar);

  const tuyos =
    ponderados.coeficiente === null
      ? `Tus ingresos (${formatEur(ponderados.importe)})`
      : `Tus ingresos ponderados (${formatEur(ponderados.importe)}, con el coeficiente ${formatNumero(ponderados.coeficiente)})`;
  let comparacion: string;
  if (lado === 'max') comparacion = cumple ? 'no superan el máximo' : 'superan el máximo';
  else comparacion = cumple ? 'alcanzan el mínimo' : 'no llegan al mínimo';
  const calculo = `${formatNumero(veces)} veces el IPREM de ${iprem.anio} en ${iprem.pagas} pagas`;

  return resultado(
    id,
    cumple ? 'CUMPLE' : 'NO_CUMPLE',
    `${tuyos} ${comparacion} de ${formatEur(limite)} al año (${calculo}).`,
    parametro,
    sinVerificar,
  );
}

/** Warnings about the IPREM, only when some income limit was compared with it. */
function avisosIprem(
  promocion: PromocionCalculadora,
  entrada: EntradaCalculadora,
  tabla: IpremAnual[],
  usado: ContextoIprem,
): string[] {
  if (tabla.length === 0) return ['No hay datos del IPREM: no se pueden comprobar los límites de ingresos.'];
  const { iprem } = usado;
  if (!iprem) return [];
  const avisos: string[] = [];
  const deLasBases = promocion.requisitos.iprem_ejercicio.valor;
  const pedido = deLasBases ?? entrada.ejercicio;
  if (deLasBases !== null && deLasBases !== entrada.ejercicio) {
    avisos.push(
      `Las bases usan el IPREM de ${deLasBases}, no el de ${entrada.ejercicio} (el año de ingresos que has indicado). Comprueba de qué año deben ser los ingresos.`,
    );
  }
  if (iprem.sustituido) {
    avisos.push(`No tenemos el IPREM de ${pedido}: se usa el de ${iprem.anio}, el último disponible.`);
  }
  if (tabla.find((f) => f.anio === iprem.anio)?.verificado === false) {
    avisos.push(`El IPREM de ${iprem.anio} está pendiente de confirmar.`);
  }
  if (promocion.requisitos.iprem_pagas.valor === null) {
    avisos.push(
      'No consta si el IPREM se calcula con 12 o 14 pagas: se asumen 14 pagas, lo habitual en la vivienda protegida de Madrid.',
    );
  }
  const { coeficientes_ponderacion: coeficientes } = promocion.requisitos;
  if (coeficientes.valor === null && coeficientes.origen !== 'no_exigido') {
    avisos.push(
      'No consta si esta convocatoria pondera los ingresos según el número de miembros: se comparan sin ponderar, y con un coeficiente el resultado podría cambiar.',
    );
  }
  return avisos;
}

// ---------------------------------------------------------------- R3: effort rate

function paraVivienda(dormitorios: number | null): string {
  if (dormitorios === null) return 'una vivienda sin dato de dormitorios';
  if (dormitorios === 0) return 'el estudio';
  return `la vivienda de ${dormitorios} ${dormitorios === 1 ? 'dormitorio' : 'dormitorios'}`;
}

/** renta × 12 / tasa, snapped to the cent when only floating point noise separates them. */
function ingresoMinimo(renta: number, tasa: number): number {
  const exacto = (renta * 12) / tasa;
  const centimos = Math.round(exacto * 100) / 100;
  return Math.abs(centimos - exacto) < MARGEN ? centimos : exacto;
}

function evaluarTipologias(
  promocion: PromocionCalculadora,
  ingresos: number | null,
): ResultadoTipologia[] {
  const parametro = promocion.requisitos.tasa_esfuerzo_max;
  const noExigida = parametro.valor === null && parametro.origen === 'no_exigido';
  const tasa = positivo(parametro.valor);
  return promocion.tipologias.map(({ dormitorios, renta_mensual_eur }) => {
    const renta = positivo(renta_mensual_eur);
    const minimo = tasa === null || renta === null ? null : ingresoMinimo(renta, tasa);
    let estado: ResultadoTipologia['estado'] = 'DESCONOCIDO';
    if (noExigida) estado = 'CUMPLE';
    else if (tasa !== null && renta !== null && ingresos !== null) {
      estado = renta * 12 <= tasa * ingresos + MARGEN ? 'CUMPLE' : 'NO_CUMPLE';
    }
    return { dormitorios, renta_mensual_eur, estado, ingreso_minimo_anual: minimo };
  });
}

/** "necesitas al menos X €/año para …", one phrase per dwelling type with a known figure. */
function necesidades(tipologias: ResultadoTipologia[]): string {
  const frases = tipologias.flatMap((t) =>
    t.ingreso_minimo_anual === null
      ? []
      : [`al menos ${formatEur(t.ingreso_minimo_anual)} al año para ${paraVivienda(t.dormitorios)}`],
  );
  return [...new Set(frases)].join('; ');
}

function reglaTasa(
  promocion: PromocionCalculadora,
  ingresos: number | null,
  tipologias: ResultadoTipologia[],
): ResultadoRegla {
  const parametro = promocion.requisitos.tasa_esfuerzo_max;
  const regla = (estado: EstadoRegla, explicacion: string) =>
    resultado('tasa_esfuerzo', estado, explicacion, parametro);

  if (parametro.valor === null && parametro.origen === 'no_exigido') {
    return regla('CUMPLE', 'Las bases no limitan la parte de los ingresos que puede suponer la renta.');
  }
  const tasa = positivo(parametro.valor);
  if (tasa === null) {
    return regla(
      'DESCONOCIDO',
      'No consta qué parte de los ingresos puede suponer como máximo la renta: consulta las bases.',
    );
  }
  const porcentaje = `${formatNumero(tasa * 100)} %`;
  const cumplen = tipologias.filter((t) => t.estado === 'CUMPLE');
  if (cumplen.length > 0) {
    return regla(
      'CUMPLE',
      `La renta puede suponer hasta el ${porcentaje} de tus ingresos y te alcanza: necesitas ${necesidades(cumplen)}.`,
    );
  }
  if (tipologias.length > 0 && tipologias.every((t) => t.estado === 'NO_CUMPLE')) {
    const [barata] = [...tipologias].sort((a, b) => a.ingreso_minimo_anual! - b.ingreso_minimo_anual!);
    return regla(
      'NO_CUMPLE',
      `Ninguna renta cabe en el ${porcentaje} de tus ingresos: la más barata exige ${necesidades([barata!])}.`,
    );
  }
  const conocidas = necesidades(tipologias);
  const detalle = conocidas ? ` Con las rentas conocidas necesitas ${conocidas}.` : '';
  const motivo =
    ingresos === null
      ? 'Indica los ingresos para comprobar la renta.'
      : 'Faltan rentas para saber si alguna vivienda te alcanza.';
  return regla('DESCONOCIDO', `La renta puede suponer hasta el ${porcentaje} de los ingresos. ${motivo}${detalle}`);
}

// ---------------------------------------------------------------- R4: registered residence

type Padron = NonNullable<PromocionCalculadora['requisitos']['empadronamiento']['valor']>;
type Comprobacion = 'si' | 'no' | 'sin_dato';

/** Whether one place of the person (home or work) satisfies the requirement. */
function comprobarLugar(
  padron: Padron,
  aniosMinimos: number,
  municipio: string | null,
  anios: number | null,
): Comprobacion {
  if (municipio === null || municipio === '') return 'sin_dato';
  if (municipio === FUERA_DE_LA_COMUNIDAD) return 'no';
  const enElLugar =
    padron.ambito === 'comunidad' ? /^28\d{3}$/.test(municipio) : municipio === padron.municipio_ine;
  if (!enElLugar) return 'no';
  if (aniosMinimos === 0) return 'si';
  const propios = dato(anios);
  if (propios === null) return 'sin_dato';
  return propios >= aniosMinimos - MARGEN ? 'si' : 'no';
}

function reglaEmpadronamiento(promocion: PromocionCalculadora, entrada: EntradaCalculadora): ResultadoRegla {
  const parametro = promocion.requisitos.empadronamiento;
  const regla = (estado: EstadoRegla, explicacion: string) =>
    resultado('empadronamiento', estado, explicacion, parametro);
  const padron = parametro.valor;

  if (padron === null) {
    return parametro.origen === 'no_exigido'
      ? regla('CUMPLE', 'Las bases no exigen estar empadronado en un sitio concreto.')
      : regla('DESCONOCIDO', 'No consta si exigen empadronamiento: consulta las bases.');
  }
  if (padron.ambito === 'municipio' && padron.municipio_ine === null) {
    return regla('DESCONOCIDO', 'Exigen empadronamiento en un municipio que no consta: consulta las bases.');
  }

  let lugar = 'la Comunidad de Madrid';
  if (padron.ambito === 'municipio') {
    lugar =
      padron.municipio_ine === promocion.municipio_ine
        ? promocion.municipio
        : `el municipio con código INE ${padron.municipio_ine}`;
  }
  const minimo = dato(padron.anios_min);
  if (minimo === null) {
    return regla(
      'DESCONOCIDO',
      `Exigen empadronamiento en ${lugar}, pero no consta con qué antigüedad: consulta las bases.`,
    );
  }
  const antiguedad = minimo > 0 ? ` desde hace al menos ${formatNumero(minimo)} ${minimo === 1 ? 'año' : 'años'}` : '';
  const trabajoAdmitido = padron.alternativa_trabajo === true ? ' (o trabajar allí)' : '';
  const exigencia = `estar empadronado en ${lugar}${antiguedad}${trabajoAdmitido}`;

  const casa = comprobarLugar(padron, minimo, entrada.municipio_empadronamiento, entrada.anios_empadronamiento);
  if (casa === 'si') return regla('CUMPLE', `Cumples: exigen ${exigencia}.`);

  const trabajo = comprobarLugar(padron, minimo, entrada.municipio_trabajo, entrada.anios_trabajo);
  if (padron.alternativa_trabajo === true) {
    if (trabajo === 'si') return regla('CUMPLE', `Cumples por tu lugar de trabajo: exigen ${exigencia}.`);
    return casa === 'no' && trabajo === 'no'
      ? regla('NO_CUMPLE', `No cumples: exigen ${exigencia}.`)
      : regla('DESCONOCIDO', `Exigen ${exigencia}. Indica dónde vives y trabajas, y desde cuándo.`);
  }
  if (padron.alternativa_trabajo === null) {
    // Whether the work place counts is unknown: it matters only if it could satisfy the requirement.
    const trabajoPodriaValer =
      trabajo === 'si' ||
      (trabajo === 'sin_dato' &&
        entrada.municipio_trabajo !== null &&
        comprobarLugar(padron, 0, entrada.municipio_trabajo, null) === 'si');
    if (trabajoPodriaValer) {
      return regla(
        'DESCONOCIDO',
        `Exigen ${exigencia}. No consta si también vale trabajar allí: consulta las bases.`,
      );
    }
  }
  return casa === 'no'
    ? regla('NO_CUMPLE', `No cumples: exigen ${exigencia}.`)
    : regla('DESCONOCIDO', `Exigen ${exigencia}. Indica dónde estás empadronado y desde cuándo.`);
}

// ---------------------------------------------------------------- R5: age

function reglaEdad(promocion: PromocionCalculadora, entrada: EntradaCalculadora): ResultadoRegla {
  const parametro = promocion.requisitos.edad;
  const regla = (estado: EstadoRegla, explicacion: string) => resultado('edad', estado, explicacion, parametro);
  const limites = parametro.valor;

  if (limites === null) {
    return parametro.origen === 'no_exigido'
      ? regla('CUMPLE', 'Las bases no exigen una edad concreta.')
      : regla('DESCONOCIDO', 'No consta si hay requisito de edad: consulta las bases.');
  }
  const tramo = textoEdad({ ...limites, tipo: 'requisito' })?.toLowerCase() ?? null;
  const edad = dato(entrada.edad);
  const dentro =
    edad !== null && edad >= (limites.min ?? -Infinity) && edad <= (limites.max ?? Infinity);

  if (limites.tipo === 'cupo') {
    if (tramo === null) {
      return regla('INFORMATIVO', 'Hay un cupo reservado por edad, sin límites conocidos: consulta las bases.');
    }
    if (edad === null) {
      return regla('INFORMATIVO', `Hay un cupo reservado por edad (${tramo}): indica tu edad para saber si entras.`);
    }
    return dentro
      ? regla('INFORMATIVO', `Por tu edad optas al cupo reservado (${tramo}).`)
      : regla('INFORMATIVO', `Optas al cupo general: el cupo reservado por edad es para ${tramo}.`);
  }
  if (tramo === null) return regla('DESCONOCIDO', 'Hay requisito de edad, pero no constan los límites.');
  if (edad === null) return regla('DESCONOCIDO', `Piden tener ${tramo}: indica tu edad.`);
  return dentro
    ? regla('CUMPLE', `Cumples la edad exigida (${tramo}).`)
    : regla('NO_CUMPLE', `No cumples la edad exigida (${tramo}).`);
}

// ---------------------------------------------------------------- R6: owning another home

function reglaTitularidad(promocion: PromocionCalculadora, entrada: EntradaCalculadora): ResultadoRegla {
  const parametro = promocion.requisitos.no_titular_vivienda;
  const regla = (estado: EstadoRegla, explicacion: string) =>
    resultado('titularidad', estado, explicacion, parametro);

  if (parametro.valor === null) {
    return parametro.origen === 'no_exigido'
      ? regla('CUMPLE', 'Las bases no exigen carecer de otra vivienda.')
      : regla('DESCONOCIDO', 'No consta si se puede tener otra vivienda: consulta las bases.');
  }
  if (!parametro.valor) return regla('CUMPLE', 'No se exige carecer de otra vivienda.');
  if (entrada.titular_vivienda === null) {
    return regla('DESCONOCIDO', 'Exigen no ser titular de otra vivienda: indica si tienes alguna.');
  }
  return entrada.titular_vivienda
    ? regla(
        'NO_CUMPLE',
        'Exigen no ser titular de otra vivienda, salvo excepciones de las bases (separación, vivienda inadecuada…).',
      )
    : regla('CUMPLE', 'No eres titular de otra vivienda, como exigen.');
}

// ---------------------------------------------------------------- R7: state

const FRASES_ESTADO: Record<EstadoPromocion, string> = {
  proxima: 'Aún no abre el plazo de inscripción.',
  inscripcion_abierta: 'La inscripción está abierta.',
  inscripcion_cerrada: 'La inscripción está cerrada.',
  sorteo_adjudicacion: 'Está en fase de sorteo o adjudicación.',
  lista_espera_abierta: 'Hay lista de espera abierta.',
  finalizada: 'La convocatoria está finalizada.',
  desconocido: 'No consta en qué estado está la convocatoria.',
};

function reglaEstado(promocion: PromocionCalculadora): ResultadoRegla {
  const retirada = promocion.activa_en_fuente ? '' : ' Ya no aparece en la web de origen.';
  return {
    id: 'estado',
    estado: 'INFORMATIVO',
    explicacion: `${FRASES_ESTADO[promocion.estado]}${retirada}`,
    origen: null,
    sin_verificar: false,
  };
}

// ---------------------------------------------------------------- one promotion

export const evaluarPromocion: EvaluarPromocion = (promocion, entrada, iprem) => {
  const usado: ContextoIprem = { iprem: null };
  const deIngresos = [
    reglaIngresos('max', promocion, entrada, iprem, usado),
    reglaIngresos('min', promocion, entrada, iprem, usado),
  ];
  // The effort rate uses the income as typed, never the weighted one.
  const ingresos = dato(entrada.ingresos_anuales);
  const tipologias = evaluarTipologias(promocion, ingresos);
  const reglas = [
    ...deIngresos,
    reglaTasa(promocion, ingresos, tipologias),
    reglaEmpadronamiento(promocion, entrada),
    reglaEdad(promocion, entrada),
    reglaTitularidad(promocion, entrada),
    reglaEstado(promocion),
  ];

  const incumplida = reglas.find((r) => r.estado === 'NO_CUMPLE');
  let veredicto: Veredicto = 'elegible';
  if (incumplida) veredicto = 'no_elegible';
  else if (reglas.some((r) => r.estado === 'DESCONOCIDO' || r.sin_verificar)) veredicto = 'posiblemente';

  return {
    promocion,
    veredicto,
    reglas,
    tipologias,
    motivo_no_elegible: incumplida?.explicacion ?? null,
    avisos: avisosIprem(promocion, entrada, iprem, usado),
  };
};

// ---------------------------------------------------------------- all promotions

const ORDEN_VEREDICTO: Record<Veredicto, number> = { elegible: 0, posiblemente: 1, no_elegible: 2 };
const alfabetico = new Intl.Collator('es', { numeric: true, sensitivity: 'base' });

/** Cheapest known rent; Infinity (sorts last) when none is known. */
function rentaDesde(promocion: PromocionCalculadora): number {
  return Math.min(...promocion.tipologias.map((t) => positivo(t.renta_mensual_eur) ?? Infinity), Infinity);
}

function comparar(a: ResultadoPromocion, b: ResultadoPromocion): number {
  const abierta = (r: ResultadoPromocion) => (r.promocion.estado === 'inscripcion_abierta' ? 0 : 1);
  const rentaA = rentaDesde(a.promocion);
  const rentaB = rentaDesde(b.promocion);
  return (
    ORDEN_VEREDICTO[a.veredicto] - ORDEN_VEREDICTO[b.veredicto] ||
    abierta(a) - abierta(b) ||
    // Compared, not subtracted: Infinity - Infinity is NaN.
    (rentaA === rentaB ? 0 : rentaA < rentaB ? -1 : 1) ||
    alfabetico.compare(a.promocion.nombre, b.promocion.nombre) ||
    (a.promocion.id < b.promocion.id ? -1 : a.promocion.id > b.promocion.id ? 1 : 0)
  );
}

/** true only when every dwelling type is known to have fewer bedrooms than wanted. */
function seQuedaCorta(promocion: PromocionCalculadora, minimo: number | null): boolean {
  const { tipologias } = promocion;
  return (
    minimo !== null &&
    tipologias.length > 0 &&
    tipologias.every((t) => t.dormitorios !== null && t.dormitorios < minimo)
  );
}

export const evaluarTodas: EvaluarTodas = (promociones, entrada, iprem, opciones) =>
  promociones
    .filter(
      (p) =>
        (opciones.mostrarFinalizadas || p.estado !== 'finalizada') && !seQuedaCorta(p, entrada.dormitorios_min),
    )
    .map((p) => evaluarPromocion(p, entrada, iprem))
    .sort(comparar);
