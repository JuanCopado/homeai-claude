// Ejecuta todos los tests del proyecto. tests/design-state.test.mjs no llegó al
// repositorio en la subida inicial: si falta, se avisa en vez de abortar antes de
// ejecutar el resto (antes `npm test` fallaba sin llegar a planner-geometry).
import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
const tests=['tests/design-state.test.mjs','planner-geometry.test.cjs'];
let failed=false,missing=[];
for(const file of tests){
  if(!existsSync(file)){missing.push(file);continue}
  const r=spawnSync(process.execPath,[file],{stdio:'inherit'});
  if(r.status!==0)failed=true;
}
if(missing.length)console.warn(`AVISO: faltan tests en el repositorio y no se han ejecutado: ${missing.join(', ')}`);
process.exit(failed?1:0);
