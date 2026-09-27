// ESLint config for HomeAI.
//
// El proyecto NO usa módulos ES ni bundler para su código de producción: cada
// archivo .js se carga con <script defer> directamente en index.html y todos
// comparten el mismo scope global (funciones y variables definidas en app.js
// se usan desde photo-studio.js, room-planner.js, etc). Por eso `sourceType`
// es "script", no "module", y declaramos como globals las funciones/variables
// que un archivo define y otro consume — así ESLint no las marca como
// "no-undef" pero SÍ avisa si de verdad falta algo.
import js from '@eslint/js';

const crossFileGlobals = {
  // definidas en app.js, usadas por los módulos v16/v17
  $: 'readonly', $$: 'readonly', esc: 'readonly', fmt: 'readonly', toast: 'readonly',
  project: 'writable', saveState: 'writable', saveSoon: 'readonly', checkpoint: 'readonly',
  undo: 'readonly', redo: 'readonly', roomKey: 'readonly',
  stableRoomId: 'readonly', renderBudget: 'readonly',
  renderTasks: 'readonly', renderDocs: 'readonly',
  renderModel: 'readonly', renderMini: 'readonly', addNavHandlers: 'readonly',
  colorOptions: 'readonly', money: 'readonly', defaultCurrency: 'readonly', budgetTotal: 'readonly',
  download: 'readonly', wallSegments: 'writable', minX: 'writable', minY: 'writable',
  maxX: 'writable', maxY: 'writable',
  // 'renderDesign', 'goView' y 'renderOverview' se definen en app.js pero luego se
  // REASIGNAN (monkey-patch) desde catalog-v16.js/studio-pro.js/workspace-v17.js para
  // envolverlas con funcionalidad añadida en esa versión — por eso son 'writable' y
  // no 'readonly': es el mismo patrón de "capas" que styles.css/design-v16.css en CSS.
  renderDesign: 'writable', goView: 'writable', renderOverview: 'writable',
  // estado/opciones del flujo de diseño, definidas en un módulo v16/v17 y usadas en
  // otro — igual de "globals compartidas a través de <script> sueltos" que las de app.js.
  activeDesignCategory: 'writable', applyFinish: 'writable', area: 'readonly',
  bathDetailOptions: 'readonly', bathOptions: 'readonly', createDesignRoom: 'readonly',
  decorOptions: 'readonly', designDraft: 'writable', designSignature: 'readonly',
  designStages: 'readonly', filterCatalog: 'writable', floorOptions: 'readonly',
  loadDesignDraft: 'readonly', renderAll: 'writable', renderFinishList: 'writable',
  roomType: 'readonly', selectedRoom: 'writable', setDesignCategory: 'readonly',
  storeDesignDraft: 'readonly', styleOptions: 'readonly', updateDesignFlow: 'writable',
  wallFinishes: 'readonly',
  // definidas en planner-geometry.js (CommonJS module.exports) y usadas como global en el navegador
  PlannerGeometry: 'readonly',
  // APIs de terceros cargadas por <script> externo
  Tesseract: 'readonly',
};

const browserExtraGlobals = {
  confirm: 'readonly', prompt: 'readonly', location: 'readonly',
  devicePixelRatio: 'readonly', structuredClone: 'readonly',
  CSS: 'readonly', Event: 'readonly', FormData: 'readonly', DOMPoint: 'readonly',
  HTMLCanvasElement: 'readonly', ImageData: 'readonly',
};

export default [
  js.configs.recommended,
  {
    ignores: ['dist/**', 'node_modules/**', 'vite.config.mjs', 'build.mjs', 'run-tests.mjs', 'tests/**', 'planner-geometry.test.cjs'],
  },
  {
    files: ['*.js'],
    ignores: ['sw.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: {
        window: 'readonly', document: 'readonly', navigator: 'readonly', console: 'readonly',
        localStorage: 'readonly', indexedDB: 'readonly', fetch: 'readonly', Blob: 'readonly',
        URL: 'readonly', Image: 'readonly', FileReader: 'readonly', Intl: 'readonly',
        requestAnimationFrame: 'readonly', cancelAnimationFrame: 'readonly',
        setTimeout: 'readonly', clearTimeout: 'readonly', setInterval: 'readonly', clearInterval: 'readonly',
        CustomEvent: 'readonly', MutationObserver: 'readonly', ResizeObserver: 'readonly',
        module: 'writable', require: 'readonly',
        ...browserExtraGlobals,
        ...crossFileGlobals,
      },
    },
    rules: {
      // no-redeclare queda desactivado a propósito: en esta arquitectura (13 archivos
      // <script> compartiendo un único scope global) cada símbolo listado arriba lo
      // "declara" un archivo (con const/let/function) y lo consumen los demás — eso es
      // exactamente lo que no-redeclare marcaría como error en el archivo que lo define,
      // aunque sea el comportamiento correcto. La regla que sí importa aquí es no-undef:
      // detecta el símbolo que NADIE define (typo, o un archivo que se quitó del HTML).
      'no-redeclare': 'off',
      'no-unused-vars': ['warn', { args: 'none', varsIgnorePattern: '^_' }],
      'no-undef': 'error',
      'no-fallthrough': 'warn',
      'no-empty': ['warn', { allowEmptyCatch: true }],
      'no-cond-assign': ['error', 'except-parens'],
    },
  },
  {
    // Service worker: corre en su propio scope global, sin window/document.
    files: ['sw.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: {
        self: 'readonly', caches: 'readonly', fetch: 'readonly', Response: 'readonly',
        clients: 'readonly', URL: 'readonly',
      },
    },
    rules: { 'no-undef': 'error' },
  },
];
