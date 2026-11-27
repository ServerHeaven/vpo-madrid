// `npm run validate-data [-- <data dir>]`: exits non-zero if anything in data/ does not validate.
import { resolve } from 'node:path';
import { encontrarDataDir, validarDatos } from './validar.mjs';

try {
  const dataDir = process.argv[2] ? resolve(process.argv[2]) : encontrarDataDir();
  const { errores, contenidos } = validarDatos(dataDir);
  for (const error of errores) console.error(`ERROR ${error}`);
  if (errores.length > 0) {
    console.error(`${errores.length} errores`);
    process.exitCode = 1;
  } else {
    console.log(`data/ es válido (${Object.keys(contenidos).length} ficheros)`);
  }
} catch (error) {
  console.error(`ERROR ${error.message}`);
  process.exitCode = 1;
}
