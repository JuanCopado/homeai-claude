# DIGITAL_TWIN_ARCHITECTURE.md — diseño del "gemelo digital" de vivienda

> Documento de **diseño**, no de implementación. Responde al encargo de Juan de
> diseñar la arquitectura del Digital Home Twin y el pipeline
> `plano → geometría estructurada → planner` **antes** de tocar ningún modelo
> de IA nuevo. No se ha escrito código de producto para este documento; los
> únicos cambios de este trabajo son este archivo, la sección nueva de
> `CURRENT_STATE.md` y el commit que los registra.
>
> Rol: escrito siguiendo el encargo de `.claude/agents/architect.md`
> (arquitectura, modularidad, deuda técnica). Fecha: 2026-09-26.

## 0. Contexto: qué pidió Juan

Juan planteó una visión grande en 8 puntos (visión, análisis de planos, plano→3D,
IA generativa de interiores, recomendador, presupuesto automático, agentes
especializados, y un objeto central llamado "Digital Home Twin" que amarra todo
lo anterior a un único proyecto con historial de decisiones). Su propia
secuencia propuesta:

```
HomeAI actual → modelo de datos de vivienda → visión → interpretación de planos
→ Digital Home Twin → 3D → generación de interiores → presupuestos
→ recomendaciones → agentes
```

Con una regla explícita que gobierna todo el diseño: **la IA generativa nunca
debe modificar silenciosamente la geometría real de la vivienda — la geometría
verificada es la fuente de verdad.**

Este documento traduce esa visión a algo anclado en el código real de HomeAI
hoy, no en una reescritura desde cero (prohibida explícitamente por Juan).

## 1. Diagnóstico: lo que el código ya hace hoy

Antes de diseñar nada hay que ser honesto sobre el punto de partida, porque no
es el que un vistazo rápido sugeriría:

- **`project.rooms`** ya implementa el principio "observado vs. confirmado" que
  Juan pide para Visión: cada `room` tiene `{id, name, type, w, d, verified,
  source, color}`. Cuando el OCR (`analyzePlan()` → `analyzeLines()`) rellena
  medidas, las marca `verified:false, source:'ocr'`; el usuario tiene que pulsar
  "Confirmar" (`renderRooms()`) para que pasen a `verified:true`. **Este patrón
  ya existe — el diseño de abajo lo generaliza, no lo inventa.**
- **`room-planner.js`** (mobiliario 2D) lleva ya en su primer comentario la
  misma regla que pide Juan para el 3D: *"A measured, editable 2D furniture
  study. Dimensions are never inferred from a photo."*
- **El hallazgo importante, que cambia el diseño**: `project.rooms` (medidas
  de habitación) y `wallSegments` (líneas de pared detectadas por
  `detectWalls()`) son **hoy dos estructuras completamente desconectadas**.
  `detectWalls()` escanea contraste de píxeles y genera segmentos de línea
  sueltos, sin relación con ninguna habitación concreta. `renderModel()` extruye
  esos segmentos en 3D, pero los nombres de habitación se dibujan en una
  **cuadrícula arbitraria de 4 columnas** (`renderModel()`, línea con
  `project.rooms.indexOf(room)%4`) — no en su posición real dentro del plano.
  No hay detección de puertas ni ventanas en ningún punto del código.
- Por tanto: **"analizar el plano y ligar habitaciones a paredes reales" no es
  una función que ya funcione parcialmente — es una función nueva**, aunque se
  apoye en piezas que sí existen (OCR, escaneo de líneas). Esto es justo lo
  que Juan pide en su punto 2, y es razonable que sea el núcleo del diseño.

## 2. Principio rector (aplicado a todo el modelo de datos)

Generalizar el patrón `verified`/`source` que ya existe en `room` a **toda**
entidad geométrica nueva (paredes, puertas, ventanas). Cada una lleva:

```js
{
  ...datosPropios,
  source: 'measured' | 'manual' | 'ocr' | 'vision' | 'user-confirmed',
  confidence: 0..1,   // 1 cuando source es 'measured'/'manual'/'user-confirmed'
  verified: true|false
}
```

Y una separación estricta en dos capas dentro del propio esquema, para que la
regla de Juan ("la IA generativa nunca toca la geometría verificada en
silencio") sea una restricción de **estructura de datos**, no solo una buena
intención de quien escriba el código:

- **Capa técnica** (`project.twin.geometry`): paredes, huecos, habitaciones,
  medidas, instalaciones. Solo se escribe por acciones explícitas del usuario
  (confirmar, editar, calibrar) o por un pipeline de interpretación que marca
  su salida como no verificada hasta confirmación.
- **Capa generativa** (`project.twin.design` — hoy ya existe como
  `project.designDrafts`/`project.finishes`): estilo, materiales, mobiliario,
  decoración, propuestas visuales. Puede leer la capa técnica pero nunca
  escribirla.

## 3. Modelo de datos: Digital Home Twin

Extensión de `freshProject()`, **aditiva y retrocompatible** (ningún campo
existente se renombra ni se elimina; un proyecto guardado hoy sigue cargando
sin migración obligatoria — `project.twin` se crea vacío/derivado si no existe,
igual que ya hace `migrateRoomIds()` con `room.id`):

```js
project.twin = {
  source: {                       // punto 1 de Juan: de dónde vino la info
    kind: 'plan-pdf'|'plan-image'|'photo'|'video'|'sketch'|'listing'|'manual',
    originalDocId: '<id en project.documents>',  // reutiliza lo que ya existe
  },
  geometry: {                     // CAPA TÉCNICA — fuente de verdad
    walls: [
      { id, x1,y1,x2,y2, thickness, roomIds:[...], source, confidence, verified }
    ],
    openings: [                   // puertas y ventanas — no existe hoy, es nuevo
      { id, wallId, kind:'door'|'window', offset, width, source, confidence, verified }
    ],
    // project.rooms sigue siendo la lista de habitaciones (no se duplica);
    // se le añade una referencia a qué paredes la delimitan:
    // room.wallIds = ['w1','w2','w3','w4']
  },
  model3d: {                      // referencia, no duplica renderModel()
    lastBuiltAt, wallHeight: project.wallHeight, exportedObjAt
  },
  decisionLog: [                  // punto 8 de Juan: historial de decisiones
    { at, actor:'user'|'ocr'|'vision'|'ai-design', change, before, after }
  ]
}
```

Notas de diseño deliberadas:

- **No se crea un `project.twin.materials`/`mobiliario`/`presupuesto`
  duplicado**: ya existen (`project.finishes`, `project.costs`,
  `project.designDrafts`). `twin` los referencia por `roomId`, no los repite —
  justo para no crear dos fuentes de verdad del mismo dato, que es el error que
  se está corrigiendo con `geometry`.
- **`decisionLog` es aditivo y opcional en el primer corte**: registrar cada
  cambio (p. ej. "cambiaste el suelo por madera") es lo que permitiría en el
  futuro la propagación que pide Juan en su punto 8 (cambiar un material y que
  se actualice presupuesto/alternativas), pero eso es una capa de
  eventos/observadores sobre las funciones `render*` ya existentes, no una
  reescritura de ellas — se puede añadir sin tocar su lógica interna.
- **`room.wallIds`** es el cambio de mayor impacto real: es lo que convierte
  "una lista de habitaciones" y "una lista de líneas" en un plano navegable de
  verdad, y es prerequisito de que el 3D deje de usar la cuadrícula arbitraria.

## 4. Pipeline: plano → geometría estructurada → planner

Mapeo directo del punto 2 de Juan a las funciones reales de `app.js`,
identificando qué existe, qué es una extensión determinista (sin IA nueva) y
qué es genuinamente nuevo y necesitaría un modelo:

| Paso | Hoy | Diseño propuesto | ¿Necesita modelo/servicio nuevo? |
|---|---|---|---|
| Cargar PDF/imagen | `loadPlan()` ✅ existe | Sin cambios | No |
| Detección de paredes | `detectWalls()` ✅ existe (heurística de contraste) | Sin cambios en el algoritmo; su salida pasa a `project.twin.geometry.walls` con `source:'vision-heuristic'` | No |
| **Puertas/ventanas** | ❌ no existe | Heurística local: un hueco es una interrupción de longitud típica (0.6–1.2 m) dentro de un segmento de pared ya detectado — determinista, sin ML, primer intento razonable | No, en su primera versión |
| OCR de cotas | `analyzeLines()` ✅ existe (una única regex, frágil) | Ampliar tolerancia de formatos (ya identificado en la auditoría técnica del 2026-09-26); sin cambiar el enfoque | No |
| **Detección de habitaciones ligadas a paredes** | ❌ no existe (hoy son dos listas sueltas) | Nuevo: algoritmo geométrico determinista que asocia cada `room` a los `walls` que la delimitan por proximidad/cierre de polígono | No — es geometría, no visión |
| Escala | `project.scale`/calibración manual ✅ existe | Sin cambios | No |
| **Visión real** (fotos, vídeo, croquis a mano, capturas inmobiliarias) | ❌ no existe — hoy solo hay OCR de texto y contraste de píxeles, no reconocimiento de objetos/mobiliario/deterioros | Requeriría un modelo de visión entrenado (local, si existe uno suficientemente ligero para navegador, o remoto) | **Sí — decisión de producto explícita, no una tarea de una sesión** |

Los tres primeros pasos de esta tabla se pueden construir con el código y las
librerías que el proyecto ya tiene (Tesseract.js, canvas, geometría de
`planner-geometry.js` extendida) — es trabajo de Architect + AI Engineer sin
necesidad de aprobar antes ningún backend ni coste externo. El último paso
(visión real sobre fotos/vídeo) es el único que obliga a la decisión de
backend/coste que ya se planteó y que Juan no ha cerrado todavía.

## 5. Hoja de ruta por fases (ajustada al orden que propuso Juan)

No se numera por prioridad de negocio sino por dependencia técnica real —
cada fase es la base de datos/contrato que la siguiente necesita:

1. **Modelo de datos** (`project.twin.geometry`, `room.wallIds`,
   `openings`) — sin UI nueva visible todavía. Riesgo bajo: solo añade campos.
2. **Ligar paredes a habitaciones** — determinista, local. Es la primera vez
   que el 3D (`renderModel()`) puede dibujar cada habitación en su posición
   real en vez de la cuadrícula arbitraria actual. Requiere red de seguridad
   visual (Playwright) antes de tocar `renderModel()`, que hoy funciona.
3. **Puertas/ventanas por heurística local** — mismo enfoque de riesgo que el
   punto 2.
4. **Decisión de producto: visión real** — aquí es donde Juan tiene que decidir
   alcance/coste/proveedor antes de que nadie escriba código; ver sección 6.
5. **IA generativa de interiores** respetando la separación de capas de la
   sección 2 — reutiliza `project.designDrafts`/`project.finishes`, solo
   cambia quién los rellena.
6. **Presupuesto conectado a geometría real** — ya hay base
   (`costQuantity()`, `calculateWallLength()`); con paredes ligadas a
   habitaciones, las cantidades por estancia dejan de ser una estimación
   global y pueden desglosarse por habitación.
7. **Recomendador** (presupuesto + familia + preferencias → alternativas
   A/B/C) — capa de reglas/heurística sobre los datos ya estructurados, no
   necesita IA generativa por sí sola.
8. **Agentes especializados dentro de HomeAI** (orquestador de cara al
   usuario final, distinto de los agentes de Claude Code que desarrollan
   HomeAI) — el último paso, porque necesita que todo lo anterior exista como
   dato estructurado con el que un orquestador pueda razonar.

## 6. Qué es local hoy y qué exigiría backend/coste, por fase

- **Fases 1–3 y 6–7: 100% local**, sin cambiar la promesa actual del
  `README.md` ("nada se envía a un servicio"). No requieren aprobación de
  Security más allá de la revisión normal de código.
- **Fase 4 (visión real) y, si se implementa con un LLM, fase 5 (generación de
  interiores con lenguaje natural, "conviértelo en estilo japandi")**: aquí sí
  se introduciría por primera vez una llamada a un servicio externo con coste
  por uso y latencia — el mismo punto que ya señaló Security en la auditoría
  del 2026-09-26. Antes de escribir una sola línea de esa fase hace falta que
  Juan apruebe explícitamente: qué proveedor, coste aproximado por uso, y qué
  pasa si el servicio falla (el proyecto debe seguir funcionando sin red,
  como hoy).
- **Fase 8 (agentes dentro de HomeAI)**: depende de qué tan "razonador" se
  quiera que sea el orquestador — una versión con reglas fijas es local; una
  versión que interpreta lenguaje natural libre ("tengo 25.000€, somos 4...")
  necesita un LLM, con el mismo punto de decisión que la fase 4.

## 7. Qué NO cambia (restricciones duras, ya impuestas por Juan)

- No se sustituye Tesseract.js, no se introduce un bundler real, no se tocan
  las 9 hojas de CSS ni el patrón de carga de los 11 `.js` — todo lo de este
  documento vive en `app.js` (o un archivo nuevo versionado, siguiendo el
  patrón `catalog-v16.js`/`workspace-v17.js` que ya usa el proyecto) sin
  romper el scope global compartido.
- Un proyecto guardado en `localStorage` hoy debe poder abrirse mañana sin
  pasos manuales — `project.twin` se deriva/crea vacío si no existe, igual que
  ya hace el código con `room.id` en `migrateRoomIds()`.
- Nada de esto se implementa todavía. Este documento es la base para que,
  cuando Juan decida avanzar, Architect y AI Engineer trabajen sobre un
  contrato de datos ya acordado en vez de improvisarlo cambio a cambio.

## 8. Siguiente paso concreto recomendado

Empezar por la sección 3 (modelo de datos) y la fase 2 de la sección 5 (ligar
paredes a habitaciones): es la pieza de mayor impacto visible (el 3D deja de
mostrar habitaciones en una cuadrícula arbitraria y pasa a mostrar el plano
real), tiene coste de implementación bajo, es 100% local, y no depende de
ninguna decisión de producto pendiente — a diferencia de la visión real
(fotos/vídeo), que si se aborda antes obligaría a decidir proveedor y coste
sin tener aún la base de datos que esa función necesitaría de todos modos.

> **Estado: fases 1-3 implementadas y verificadas (2026-09-26) — es hasta
> donde llega lo 100% local.** Ver `CURRENT_STATE.md` para el detalle: fase 1,
> ligar paredes a habitaciones (`computeRoomRegions`/`matchRoomsToRegions` en
> `planner-geometry.js`, `linkRoomsToWalls()` en `app.js`, reactivo a
> cualquier edición de medidas); fase 2, detección de huecos
> (`detectOpenings()`, `detectWallOpenings()`, dibujado en
> `renderWallEditor()`, deliberadamente sin distinguir puerta de ventana);
> fase 3, una partida de presupuesto conectada a los huecos detectados
> (`qtyType:'openings'` en `costQuantity()`). Cada una con su evidencia de
> verificación (tests, lint, build, Playwright), sin regresiones acumuladas.
>
> Lo que queda del plan de 8 puntos de Juan (visión real, generación de
> interiores por lenguaje natural, un orquestador de frases libres) no es un
> siguiente incremento de esta misma naturaleza: los tres necesitan un LLM o
> una API de visión externa — proveedor, credenciales y coste real que no
> existen en este entorno y que no se deben comprometer sin aprobación
> explícita de Juan, porque cambian la promesa actual de "nada sale del
> dispositivo". Un recomendador por reglas fijas sería posible sin LLM, pero
> es una función nueva y no una mejora incremental sobre lo que ya existe —
> se documentó en vez de construirse sin revisión.
>
> **2026-09-26, más tarde**: se investigaron proveedores/precios concretos
> (de pago, gratuitos y autoalojados) para las tres capacidades que faltan —
> ver `PROVEEDORES_IA.md`. La conclusión más importante de esa investigación
> no es qué proveedor es más barato, sino que HomeAI al ser hoy una app sin
> backend, cualquier API de pago obliga primero a decidir dónde vive la
> clave (backend propio, clave del propio usuario, o quedarse en opciones
> 100% locales) — esa decisión de arquitectura es anterior a elegir
> proveedor y sigue pendiente de que Juan la resuelva.
