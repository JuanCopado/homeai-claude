# PROJECT.md — qué es HomeAI y cómo está construido

Contexto técnico para los agentes. La descripción orientada al usuario final está
en `README.md`; este archivo es la orientación rápida para quien va a tocar código.

## Qué es

HomeAI es una web app de planificación integral de reforma: importar un plano,
calibrar su escala, reconocer estancias, generar una maqueta 3D conceptual,
elegir acabados/materiales por estancia, presupuestar y organizar el plan de obra.
Todo corre **en el navegador del usuario**, sin backend propio.

## Stack

- Sin framework. HTML/CSS/JS planos. `package.json` solo usa Vite como servidor de
  desarrollo (`npm run dev`); la build real (`npm run build`) es `build.mjs`, un
  script que copia archivos a `dist/` — no hay bundling ni transpilación.
- **JS: 13 archivos `<script defer>` cargados directamente en `index.html`, sin
  módulos ES, compartiendo un único scope global.** Orden y responsabilidad:
  `app.js` (estado del proyecto, presupuesto, tareas, plano, calibración de
  escala, undo/redo, exportar/restaurar copia de seguridad) →
  `catalog-enhancements.js` → `alternatives.js` → `photo-studio.js` (estudio
  fotográfico, OCR) → `studio-pro.js` → `catalog-v16.js` → `advisor-v16.js` →
  `planner-geometry.js` (geometría pura, también usada vía `require` en tests) →
  `room-planner.js` → `material-library.js` → `workspace-v17.js` →
  `ai-orchestrator.js` (asistente WebLLM, local) → `ai-interior-preview.js`
  (imagen de inspiración, Stable Diffusion en navegador). Varios de estos
  archivos **reasignan (monkey-patch) funciones definidas en `app.js`**
  (`renderDesign`, `goView`, `renderOverview`, `filterCatalog`, etc.) para añadir
  comportamiento de esa versión — es el mismo patrón de "capas" que en el CSS.
  La lista completa de símbolos compartidos entre archivos está en
  `eslint.config.mjs` (`crossFileGlobals`); si se añade o se quita uno, hay que
  actualizar esa lista.
- **CSS: 11 hojas cargadas en orden fijo** (`styles.css` → `studio.css` →
  `studio-pro.css` → `catalog-v16.css` → `design-v16.css` → `advisor-v16.css` →
  `room-planner.css` → `material-library.css` → `workspace-v17.css` →
  `ai-orchestrator.css` → `ai-interior-preview.css`), cada una
  correspondiente a una versión que re-tematiza a propósito selectores de las
  anteriores. Detalle completo, con qué es intencional y qué es deuda real, en
  `CSS_AUDIT.md`.
- **Persistencia**: `localStorage` (`STORE_KEY = 'renovioStudioProject.v2'`, todo
  el objeto `project`) + IndexedDB (`homeai-project-files` para documentos/fotos
  como blobs). No hay cuenta en la nube ni sincronización: el login "Continuar con
  ChatGPT" solo controla el acceso al sitio publicado en
  `homeai.juancopado.chatgpt.site`, es independiente de los datos del proyecto.
- **Hosting**: publicado como "ChatGPT Library site artifact" vía
  `.openai/hosting.json` (`static.directory: "dist"`). El repo de referencia es
  `https://github.com/JuanCopado/HOMEAI.git`.

## Funciones IA/visión ya existentes (relevante para AI Engineer)

- **OCR**: Tesseract.js (español), carga bajo demanda al usar "Leer con IA";
  procesa la imagen en el dispositivo, no la envía a ningún servicio.
- **Detección de muros**: heurística de píxeles oscuros sobre un canvas
  (`detectWalls()` en `app.js`) — no es un modelo de visión entrenado, es un
  escaneo de contraste por filas/columnas. Cualquier mejora real de precisión
  (segmentación semántica, un modelo entrenado) es trabajo de AI Engineer y hoy
  no existe.
- **Maqueta 3D**: extrusión conceptual de los muros vectorizados sobre un canvas
  2D con proyección manual (no WebGL, no motor 3D real); exporta `.obj`/`.mtl`.
  No resuelve habitaciones con precisión BIM (ver limitaciones en `README.md`).
- No hay ninguna llamada a un LLM ni a una API de terceros con coste por token en
  este momento — todo el procesamiento "IA" actual es local. Si se añade algo que
  sí llame a un modelo externo, es el primer caso que necesita revisión de
  Security (claves, coste, latencia, qué datos salen del dispositivo).

## Verificación (lo que QA/todo agente debe ejecutar antes de dar algo por terminado)

```
npm test          # run-tests.mjs: tests/design-state.test.mjs + planner-geometry.test.cjs
npm run lint      # eslint . && stylelint "*.css"
node build.mjs    # regenerar dist/ tras cualquier cambio de app.js/*.css
```

CI en `.github/workflows/ci.yml` (`npm test` + `npm run lint:js` en cada push/PR; `lint:css` no se incluye mientras sigan los 70 duplicados conocidos de `styles.css`). La verificación visual se hace localmente: servir
`dist/` con `python3 -m http.server` y recorrer las vistas
(`overview`, `plan`, `model`, `design`, `budget`, `tasks`, `docs`) en varios
anchos (390/921/1440px, mínimo) con Playwright
(`chromium.launch({ executablePath: '/opt/pw-browsers/chromium' })`), comparando
antes/después. Es el patrón ya usado en las auditorías registradas en
`CHANGELOG_CLAUDE.md` y `CSS_AUDIT.md`.

## Documentos a leer según la tarea

- `README.md` — features y alcance real, cara al usuario.
- `CHANGELOG_CLAUDE.md` — historial de bugs corregidos y por qué.
- `CSS_AUDIT.md` — por qué las 11 hojas de CSS no se han fusionado en una.
- `eslint.config.mjs` / `.stylelintrc.json` — reglas de lint y su razón de ser.
- `CURRENT_STATE.md` — estado vivo del proyecto; leer siempre antes de empezar.
- `DIGITAL_TWIN_ARCHITECTURE.md` — diseño (no implementado aún) del modelo de
  datos y pipeline plano→geometría→planner para la visión ampliada de HomeAI
  (visión, planos, 3D real, generación de interiores, presupuesto automático,
  agentes internos). Leer antes de tocar `detectWalls()`, `project.rooms`,
  `renderModel()` o cualquier trabajo de AI Engineer en esa dirección.
- `PROVEEDORES_IA.md` — investigación de proveedores/precios (de pago,
  gratuitos y autoalojados) para las fases que sí necesitan un modelo
  externo (visión real, generación de interiores, orquestador de lenguaje
  natural). Leer antes de elegir o integrar cualquier API de IA externa —
  incluye el problema de arquitectura (dónde vive la API key) que hay que
  resolver antes de elegir proveedor.
