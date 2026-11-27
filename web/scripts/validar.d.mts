export function encontrarDataDir(desde?: string): string;

export function validarDatos(dataDir: string): {
  errores: string[];
  contenidos: Record<string, unknown>;
};
