// Turns the raw text of the form into the engine's EntradaCalculadora. Pure: no markup, no state.
// A blank field is always null (never 0 or false); a value we cannot read is an error, not a guess.
import { FUERA_DE_LA_COMUNIDAD, type EntradaCalculadora, type Municipio } from '../lib/contratos-calculadora';
import { estimarBaseImponible } from '../lib/eligibility';

export interface Campos {
  ingresos: string;
  soloBruto: boolean;
  ejercicio: string;
  miembros: string;
  empadronamiento: string;
  empadronamientoFuera: boolean;
  aniosEmpadronamiento: string;
  trabajo: string;
  trabajoFuera: boolean;
  aniosTrabajo: string;
  edad: string;
  titular: '' | 'si' | 'no';
  dormitorios: string;
}

export const CAMPOS_VACIOS: Campos = {
  ingresos: '',
  soloBruto: false,
  ejercicio: '',
  miembros: '',
  empadronamiento: '',
  empadronamientoFuera: false,
  aniosEmpadronamiento: '',
  trabajo: '',
  trabajoFuera: false,
  aniosTrabajo: '',
  edad: '',
  titular: '',
  dormitorios: '',
};

export type Errores = Partial<Record<keyof Campos, string>>;

export type Lectura = { entrada: EntradaCalculadora; errores: null } | { entrada: null; errores: Errores };

/**
 * A non-negative amount as typed in Spain: "30000", "30.000", "30 000,50 €". A single dot followed
 * by one or two digits is read as a decimal point. null when blank or unreadable.
 */
export function leerNumero(texto: string): number | null {
  let t = texto.replace(/[\s€]/g, '');
  if (/^\d{1,3}(\.\d{3})+(,\d+)?$/.test(t)) t = t.replaceAll('.', '').replace(',', '.');
  else if (/^\d+(,\d+)?$/.test(t)) t = t.replace(',', '.');
  else if (!/^\d+\.\d{1,2}$/.test(t)) return null;
  return Number(t);
}

const normalizar = (texto: string): string =>
  texto.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().replace(/\s+/g, ' ').trim();

const sinArticulo = (texto: string): string => texto.replace(/^(el|la|los|las) /, '');

/** INE code of the municipality typed, ignoring case, accents and a missing article. */
export function buscarMunicipio(texto: string, municipios: Municipio[]): string | null {
  const buscado = normalizar(texto);
  if (buscado === '') return null;
  const exacto = municipios.find((m) => normalizar(m.nombre) === buscado);
  if (exacto) return exacto.ine;
  const parecidos = municipios.filter((m) => sinArticulo(normalizar(m.nombre)) === sinArticulo(buscado));
  return parecidos.length === 1 ? parecidos[0]!.ine : null;
}

export function leerCampos(campos: Campos, municipios: Municipio[]): Lectura {
  const errores: Errores = {};

  const ingresos = leerNumero(campos.ingresos);
  if (ingresos === null) {
    errores.ingresos =
      campos.ingresos.trim() === ''
        ? 'Escribe los ingresos anuales.'
        : 'No entendemos la cantidad. Escribe solo números, por ejemplo 28.500.';
  }

  const miembros = campos.miembros === '' ? null : Number(campos.miembros);
  if (miembros === null) errores.miembros = 'Elige cuántas personas forman la unidad de convivencia.';

  const ejercicio = Number(campos.ejercicio);
  if (!Number.isInteger(ejercicio) || ejercicio <= 0) errores.ejercicio = 'Elige el año de los ingresos.';

  function municipio(clave: 'empadronamiento' | 'trabajo', fuera: boolean): string | null {
    if (fuera) return FUERA_DE_LA_COMUNIDAD;
    if (campos[clave].trim() === '') return null;
    const ine = buscarMunicipio(campos[clave], municipios);
    if (ine === null) {
      errores[clave] = 'No reconocemos ese municipio. Elige uno de la lista o deja la casilla vacía.';
    }
    return ine;
  }

  function anios(clave: 'aniosEmpadronamiento' | 'aniosTrabajo', fuera: boolean): number | null {
    // Years outside the Comunidad never count: the box is disabled and its content ignored.
    if (fuera || campos[clave].trim() === '') return null;
    const valor = leerNumero(campos[clave]);
    if (valor === null || valor > 100) {
      errores[clave] = 'Escribe un número de años, por ejemplo 3 o 2,5.';
      return null;
    }
    return valor;
  }

  const municipioEmpadronamiento = municipio('empadronamiento', campos.empadronamientoFuera);
  const aniosEmpadronamiento = anios('aniosEmpadronamiento', campos.empadronamientoFuera);
  const municipioTrabajo = municipio('trabajo', campos.trabajoFuera);
  const aniosTrabajo = anios('aniosTrabajo', campos.trabajoFuera);

  let edad: number | null = null;
  if (campos.edad.trim() !== '') {
    const valor = Number(campos.edad.trim());
    if (Number.isInteger(valor) && valor >= 16 && valor <= 100) edad = valor;
    else errores.edad = 'La edad debe ser un número entero entre 16 y 100.';
  }

  if (Object.keys(errores).length > 0) return { entrada: null, errores };

  return {
    entrada: {
      ingresos_anuales: campos.soloBruto ? estimarBaseImponible(ingresos!) : ingresos!,
      ingresos_estimados: campos.soloBruto,
      ejercicio,
      miembros: miembros!,
      municipio_empadronamiento: municipioEmpadronamiento,
      anios_empadronamiento: aniosEmpadronamiento,
      municipio_trabajo: municipioTrabajo,
      anios_trabajo: aniosTrabajo,
      edad,
      titular_vivienda: campos.titular === '' ? null : campos.titular === 'si',
      dormitorios_min: campos.dormitorios === '' ? null : Number(campos.dormitorios),
    },
    errores: null,
  };
}
