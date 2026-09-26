# Correcciones aplicadas (auditoría HomeAI, 2026-09-26)

Tres bugs de la auditoría inicial, diagnosticados sobre el código real y verificados
ejecutando la app localmente (Chromium/Playwright) antes y después de cada cambio.

## 1. "Probar con un ejemplo" no cargaba la foto de muestra

**Archivo:** `photo-studio.js`

**Causa:** `setPhoto()` valida que el blob subido tenga `type` igual a
`image/jpeg`, `image/png` o `image/webp`. El botón "Probar con un ejemplo" hace
`fetch()` de una imagen `.webp` propia del proyecto (`assets/*.webp`, confirmadas
como WebP válidas) y pasa el blob resultante a `setPhoto()`. En ciertos entornos de
hosting, el `Content-Type` que el servidor devuelve para ese `fetch()` no llega
como `image/webp`, así que la validación rechaza una imagen que en realidad es
válida y lanza "Formato no admitido."

**Arreglo:** si el blob recibido no trae uno de los tres tipos esperados, se
reconstruye con `type: 'image/webp'` (que sí sabemos correcto, porque el archivo
es nuestro) antes de pasarlo a `setPhoto()`. No se tocó la validación para fotos
que sí sube el usuario.

**Verificado:** clic en "Probar con un ejemplo" → estado pasa a "Foto y
superficies guardadas en este navegador." y el editor de foto se muestra con la
imagen cargada.

## 2. Moneda por defecto en Presupuesto (COP para todo el mundo)

**Archivo:** `app.js`

**Causa:** el valor por defecto de la moneda estaba fijo a `'COP'` en dos
lugares (`money()` y la inicialización del selector), sin detectar la región del
usuario.

**Arreglo:** nueva función `defaultCurrency()` que usa `Intl.Locale` sobre
`navigator.language` para elegir `COP` solo si la región es Colombia (`CO`), y
`EUR` en cualquier otro caso (son las dos únicas monedas que ofrece el selector).

**Verificado:** con locale `es-ES` el selector queda en `EUR`; con `es-CO`, en
`COP`.

## 3. Barra de calibración de escala (Plano) se veía apretada/rota

**Archivo:** `workspace-v17.css` (nuevas reglas al final; no se tocaron los
archivos de versiones anteriores)

**Causa:** `.plan-edit-actions{flex-wrap:wrap}` en `styles.css` solo está
activo dentro de `@media(max-width:600px)`. Entre 600 y 1200px de ancho, la fila
no puede pasar sus botones a una segunda línea, así que cada etiqueta larga
("2. Marcar esa distancia", "✎ Editar muros") se partía en varias líneas dentro
de su propia columna (por `white-space:normal` heredado de `.control-chip` en
`studio.css`), y en anchos mayores la fila simplemente se desbordaba de la
tarjeta.

**Arreglo:** se activa `flex-wrap:wrap` para `.plan-edit-actions` en todos los
anchos, y se fija `white-space:nowrap` en cada control individual para que sea
el botón completo el que salte de línea, no el texto dentro de él.

**Verificado:** a 921px de ancho (el bug original) la barra ahora ocupa dos
filas limpias, sin texto cortado ni desborde; en 390px (móvil) y en escritorio
ancho no hay regresión.

---

Todos los tests existentes (`node tests/design-state.test.mjs`,
`node planner-geometry.test.cjs`) siguen pasando tras estos cambios.

# Segunda tanda: auditoría CSS, lint y copia de seguridad (2026-09-26)

Tres mejoras aprobadas tras la primera tanda de arreglos.

## 4. Auditoría del CSS "por capas" entre las 9 hojas de estilo

Se analizó programáticamente (script Python + `tinycss2`) si los selectores
repetidos entre `styles.css`, `studio.css`, `studio-pro.css`, `catalog-v16.css`,
`design-v16.css`, `advisor-v16.css`, `room-planner.css`, `material-library.css` y
`workspace-v17.css` eran choques accidentales o restyling intencional por versión.
Detalle completo, con la explicación de por qué NO se hizo una fusión ciega de las 9
hojas en una sola (riesgo de regresión visual sin una suite de capturas
antes/después), en **`CSS_AUDIT.md`**. Se hizo además un barrido visual con
Playwright (7 vistas × 3 anchos) para confirmar que no quedan más bugs del tipo
"barra rota" además del ya corregido en la tanda anterior.

## 5. ESLint + Stylelint

Se añadió `eslint.config.mjs` (formato flat config, ESLint 9) y `.stylelintrc.json`
(Stylelint 17), con scripts `npm run lint:js`, `npm run lint:css`, `npm run lint` y
`npm test`. Ambas herramientas están ajustadas a este proyecto en particular: el JS
se carga como 11 `<script defer>` sueltos que comparten un único scope global (no
hay módulos ES ni bundler), así que ESLint declara como *globals* compartidas las
funciones/variables que un archivo define y otro consume, en vez de marcarlas como
error; y el CSS no extiende `stylelint-config-standard` porque esa configuración
asume un formato de una declaración por línea, y aquí los 9 archivos están escritos
en una sola línea a propósito — extenderla generaba >1400 falsos avisos de
formato. En su lugar se usa un conjunto de reglas centrado en detectar *errores
reales* (propiedades desconocidas, selectores duplicados dentro de un mismo
archivo, unidades inválidas, etc.), no estilo de código.

**Ya encontró un bug real al ejecutarse por primera vez:** en `workspace-v17.css`,
`.workspace-modes button{font:600 15px/1.3 inherit}` es CSS inválido (`inherit` no
puede combinarse con otros valores dentro del atajo `font`), así que el navegador
descartaba la declaración entera y los botones de "Colores y acabados / Distribución
a escala" se mostraban con el tamaño/peso/interlineado por defecto del body en vez
de los 600/15px/1.3 previstos. Se corrigió separando en
`font-weight:600;font-size:15px;line-height:1.3` (verificado con
`getComputedStyle` antes y después). Detalle en `CSS_AUDIT.md`.

`npm run lint:css` reporta hoy 70 avisos de "selector duplicado dentro del mismo
archivo" en `styles.css`, que son deuda previa a esta sesión — no se tocaron porque
arreglarlos a mano en un archivo de 83KB en una sola línea, sin poder confirmar
visualmente cuál de las dos versiones es la vigente en cada uno de los 70 casos,
tiene más riesgo que beneficio en esta pasada. Quedan documentados y visibles para
quien continúe.

## 6. Restaurar copia de seguridad (.JSON)

**Archivo:** `app.js` (nueva función `importProjectFromFile`, botón añadido en
`openExportModal`)

**Motivación:** HomeAI pide iniciar sesión (Continuar con ChatGPT) para entrar,
pero **no sincroniza nada con esa cuenta** — todo el proyecto vive sólo en
`localStorage`/IndexedDB de ese navegador concreto. Ya existía exportar el proyecto
a `.JSON` (botón "Copia de seguridad del proyecto"), pero no había manera de
restaurarlo: si el usuario cambiaba de dispositivo, limpiaba el navegador o
desinstalaba la app, la copia de seguridad no servía para nada.

**Qué se añadió:** un botón "Restaurar copia de seguridad (.JSON)" en el mismo
modal de Exportar. Lee el archivo elegido, valida que tenga la forma mínima de un
proyecto de HomeAI (`rooms` y `tasks` como arrays — la misma validación que ya se
usa al cargar `localStorage` al iniciar la app), pide confirmación explícita porque
sustituye el proyecto actual, y si el usuario confirma: reemplaza `project`, guarda
en `localStorage`, recarga el plano/las paredes/el modelo 3D y todas las vistas
(reutilizando `renderAll()`, la misma función que ya usan Deshacer/Rehacer tras
sustituir el proyecto entero). Un JSON inválido o que no tiene forma de proyecto de
HomeAI muestra un aviso y no toca el proyecto actual.

**Verificado con Playwright:** exportar → cambiar el título del proyecto → abrir
"Restaurar copia de seguridad" → cargar el JSON exportado en el paso 1 → confirmar
→ el título vuelve al original tanto en memoria como en `localStorage`. Un archivo
con JSON corrupto no cambia el proyecto y no lanza errores.

---

Tests (`npm test`) y barrido visual (Playwright, 7 vistas × 3 anchos) verificados
tras esta segunda tanda; sin regresiones.
