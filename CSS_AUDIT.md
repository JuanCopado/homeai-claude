# Auditoría CSS — arquitectura de capas (2026-09-26)

## Cómo está construido el CSS de HomeAI

`index.html` carga nueve hojas de estilo, en este orden fijo:

```
styles.css → studio.css → studio-pro.css → catalog-v16.css → design-v16.css →
advisor-v16.css → room-planner.css → material-library.css → workspace-v17.css
```

Cada archivo corresponde a una versión/iteración de la app (v13 → v16 → v17). En vez
de editar las reglas ya existentes cuando se rediseña algo, el patrón habitual en este
proyecto es **añadir un archivo nuevo al final** que redefine variables, colores,
tipografía y espaciados para los mismos selectores (`:root`, `.topbar`, `.sidebar`,
`.main-content`, `.page-head h1`, etc.). Por la cascada CSS, como esos archivos se
cargan después, sus valores gobiernan sobre los de `styles.css`/`studio.css`.

**Esto es intencional, no un bug.** Un script de auditoría (`css_audit.py`) que
compara selectores idénticos entre archivos encontró **180 selectores** con
declaraciones distintas para la misma propiedad en más de un archivo — pero al
revisarlos, son en su inmensa mayoría el propio "restyling" progresivo (colores de
`:root`, tamaños de fuente, paddings) que cada versión posterior aplica a propósito
sobre la anterior. Reescribir esto en una sola hoja "limpia" implicaría decidir, para
cada uno de esos 180 casos, cuál de las 2-4 versiones es la vigente — con el único
criterio real siendo "cuál carga al final", que es exactamente lo que ya hace la
cascada. Un rewrite así no cambiaría el comportamiento visual si se hace bien, pero sí
tiene un costo de riesgo real: cualquier selector mal copiado, cualquier `@media` que
se pierda al fusionar, rompe la app en producción sin que hay manera de probarlo todo
salvo revisando pantalla por pantalla.

## Dónde SÍ hay bugs reales (y qué se hizo)

El patrón que sí genera errores reales — y es el que causó el bug de la barra de
calibración en Plano que ya se corrigió — es distinto: **una propiedad de layout
(`flex-wrap`, `white-space`, `overflow`, `grid-template-columns`...) que sólo se fija
dentro de un `@media` en un archivo, sin que ningún archivo posterior la fije de forma
incondicional para los anchos intermedios.** Un segundo script (`css_audit2.py`)
buscó específicamente ese patrón — 88 casos encontrados — y cada uno se revisó
manualmente: la gran mayoría son el uso normal y correcto de "sólo cambio esto en
móvil" (p. ej. `.advisor-entry{flex-direction:column}` sólo bajo 600px, con `row` como
valor por defecto del navegador para flex — no hay conflicto). El caso ya corregido
(`.plan-edit-actions{flex-wrap:wrap}` sólo bajo 600px, con contenido que no cabía en
una fila entre 600 y 1200px) era la excepción real.

Para confirmarlo sin depender sólo de leer CSS, se hizo un barrido visual con
Playwright: las 7 vistas de la app (`overview`, `plan`, `model`, `design`, `budget`,
`tasks`, `docs`) en 3 anchos (390 / 921 / 1440px), detectando automáticamente
cualquier elemento cuyo `scrollWidth` exceda el ancho del documento. El único caso
detectado es `.budget-table-wrap` en móvil, que tiene `overflow-x:auto` puesto a
propósito (tabla de presupuesto con scroll horizontal en pantallas pequeñas) — no es
un desborde de página, es un contenedor con scroll interno intencional.

**Conclusión de esta pasada: no se encontraron más bugs del tipo "barra rota" además
del ya corregido.**

## Qué se hizo en esta iteración

1. Se documentó esta arquitectura (este archivo) para que futuras ediciones no
   asuman que un selector repetido en varios archivos es un error a "limpiar".
2. Se añadió Stylelint (ver `PLAN_MEJORAS.md` / `package.json`) con la regla
   `no-descending-specificity` y un lint de duplicados dentro del mismo archivo,
   que es justamente lo que hubiera marcado el bug de `.control-chip` si hubiera
   existido antes.
3. No se tocaron los 180 casos de "restyling intencional" — hacerlo sin una suite de
   regresión visual (capturas de pantalla automatizadas comparando antes/después en
   cada vista y ancho) tiene más riesgo de romper algo que beneficio, dado que
   visualmente ya funcionan correctamente.

## Stylelint ya encontró un bug real

Al añadir Stylelint (ver más abajo) con la regla `declaration-property-value-no-unknown`,
saltó un caso real en `workspace-v17.css`:

```css
.workspace-modes button{...font:600 15px/1.3 inherit;...}
```

`inherit` no es válido como parte de la lista de familia dentro del atajo `font`
(sólo es válido como valor completo de la propiedad, ej. `font-family:inherit`), así
que Chromium descarta la declaración **entera**: los botones "Colores y acabados /
Distribución a escala" se renderizaban con el tamaño, peso y alto de línea por
defecto del body (16px/400/25.6px) en vez de los 15px/600/1.3 previstos — un bug
real, silencioso, y confirmado con `getComputedStyle` antes/después. Se corrigió
separando en `font-weight:600;font-size:15px;line-height:1.3` (así `font-family`
sigue heredándose por el reset global `button,input,select{font:inherit}` de
`styles.css`, que es válido porque ahí `inherit` es el valor completo).

## Deuda conocida que queda documentada, no "arreglada a ciegas"

`no-duplicate-selectors` de Stylelint reporta 70 selectores duplicados **dentro del
mismo archivo** `styles.css` (p. ej. `.material-card`, `.style-art`, varios
`#designPreview[data-...]`). No son el patrón de capas entre archivos descrito
arriba — son repeticiones dentro de un único archivo de 83KB en una sola línea,
probablemente restos de ediciones incrementales previas. Corregirlos a mano en un
archivo minificado de ese tamaño, sin poder diferenciar visualmente con seguridad
cuál de las dos definiciones es la vigente para cada uno de los 70 casos, tiene más
riesgo de romper algo que beneficio en esta pasada. Quedan listados aquí como
`npm run lint:css` los seguirá señalando hasta que se revisen uno a uno.

## Recomendación a futuro

Si se quiere consolidar de verdad estas 9 hojas en una sola, el camino seguro es:
añadir antes una suite de *visual regression testing* (capturas Playwright de cada
vista/ancho, comparadas pixel a pixel tras cada cambio — la carpeta
`scratchpad/shots` de esta sesión es un punto de partida), y sólo entonces fusionar
archivo por archivo verificando que ninguna captura cambia. Hacerlo "a ciegas" no es
recomendable para una app ya en producción.
