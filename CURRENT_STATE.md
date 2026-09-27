# CURRENT_STATE.md — estado vivo del proyecto

> El coordinador actualiza este archivo al terminar cada tarea (qué se hizo, qué
> queda pendiente, qué deuda nueva se detectó). Es lo primero que debe leer
> cualquier agente antes de tocar nada. Última actualización: **2026-09-26**
> (auditoría técnica y funcional completa + Digital Home Twin fases 1-3 +
> investigación de proveedores de IA + implementación de dos opciones
> gratuitas/locales — orquestador WebLLM y generación de interiores con
> Stable Diffusion en navegador — ver secciones dedicadas abajo).

## Hecho

- **Visualización de reforma con IA, fase 1 (MVP) (2026-09-27).** Foto real de
  la estancia + estilo → la misma estancia redecorada, vía Hugging Face
  Inference Providers (`image_to_image`). Primera función de HomeAI que envía
  datos fuera del dispositivo; resuelve la "sección 0" de `PROVEEDORES_IA.md`
  con la opción 1 (backend propio que guarda la clave).
  - **Arquitectura:** no había backend, así que es un **microservicio aparte**
    en `server/` (FastAPI + `huggingface_hub`, `Dockerfile` listo para un
    Hugging Face Space CPU gratuito). `HF_TOKEN` solo como secreto del
    servidor. Fase 2 prevista: `HF_MODEL` → URL de un Inference Endpoint con
    SD + ControlNet, sin tocar el navegador.
  - **Pipeline:** valida formato (JPG/PNG/WebP) y tamaño, aplica orientación
    EXIF, quita metadatos, ≤1024 px múltiplo de 8, autocontraste en fotos muy
    oscuras, prompt de estilo + sufijo "misma estancia, mismas paredes y
    ventanas" + prompt negativo, `strength` 0,30–0,80. Errores de HF (402
    crédito agotado, 429, 503, timeout, token inválido, modelo no servido)
    traducidos a códigos claros. Límite por IP/hora y de concurrencia.
  - **UX** (`ai-renovation.js`/`.css`, vista Diseño): elegir foto → estilo
    (6 atajos o texto libre) + intensidad → consentimiento explícito →
    espera con contador y cancelar → comparación antes/después con
    deslizador → guardar en Archivos (IndexedDB local) / descartar / probar
    otro estilo. Desactivada mientras
    `<meta name="homeai-renovation-endpoint">` esté vacía.
  - **Privacidad:** el navegador reduce y re-codifica la foto (sin EXIF/GPS)
    antes de enviarla; el servidor no escribe nada en disco (ni temporales),
    no registra fotos ni textos y responde `no-store`.
  - **QA:** 32 tests `pytest` (fotos pequeñas, panorámicas, oscuras, PNG con
    transparencia, WebP, GIF, HEIC, JPEG truncado, EXIF con GPS y rotación,
    límites de tamaño, todos los errores de HF, rate limit, concurrencia,
    CORS, subida que no toca disco) y Playwright con API simulada a 390 y
    1440 px (validaciones, consentimiento, espera, resultado, guardar, 429,
    crédito agotado, respuesta HTML, sin red, cancelar; sin errores de
    consola ni scroll horizontal) + regresión de las 7 vistas. CI ejecuta
    también `pytest`.
  - **Prueba de punta a punta (2026-09-27):** navegador real → `server/app.py`
    arrancado con uvicorn → `huggingface_hub` real → un endpoint local que imita
    un Inference Endpoint (`HF_MODEL` = URL). Confirmado: el token viaja como
    `Bearer`, el modelo recibe prompt, prompt negativo y `strength`, la foto
    llega a 1024×768 sin EXIF, los HTTP 402/429/503/500/401 reales de la
    librería se traducen bien, CORS bloquea orígenes no permitidos, y ni el
    token ni la foto ni el texto aparecen en los logs. CI arreglado
    (`server/pytest.ini`: `pytest` sin `python -m` no encontraba `app.py`).
  - **No verificado:** ninguna llamada real a Hugging Face (el proxy de este
    entorno bloquea huggingface.co). Qué modelo sirve de verdad para
    image-to-image hay que comprobarlo con `server/check_model.py` antes de
    desplegar.

## Pendiente de la visualización con IA

- **Validación de la detección de estilo (2026-09-27, rama `claude/estilo-interior`,
  `server/validation/validate_style.py` → `results_style/`).** CLIP zero-shot,
  base/32 frente a large/14, 8 estilos. Dos rondas en GitHub Actions:
  - Muchas "etiquetas" de la búsqueda en Wikimedia eran falsas (la casa Futuro
    como "escandinavo", el Bohemian Hall checo como "bohemio", exteriores
    como "rústico"); se descartaron al revisar las fotos a mano.
  - Con 8 fotos de etiqueta fiable (rústico, industrial, minimalista,
    moderno): **large/14 acierta 7/8, base/32 3–4/8.** Tiempo en CPU:
    1,2 s frente a 0,2 s por foto.
  - Umbral "top-1 ≥ 0,5 y margen ≥ 0,2" con large/14: se sugiere en 7/8 y
    las 7 aciertan; el fallo (primer plano de una lámpara, 0,45 / +0,05)
    queda sin sugerencia.
  - Habitación vacía: sin etiquetas "sumidero" salía "minimalista" (0,97);
    con "habitación vacía" y "primer plano de objeto" como etiquetas de
    no-sugerir, 2/2 vacías quedan sin sugerencia. Falta una tercera para
    exteriores.
  - **Sin validar por falta de fotos buenas en Wikimedia:** escandinavo,
    bohemio, clásico y mediterráneo.
  - **Ronda 3 (Openverse para los estilos sin cubrir) y conclusión global:**
    Juan pidió buscar en Pinterest; se descartó (derechos de autor de terceros,
    condiciones de uso, y las fotos se guardan en el repo) y se usó Openverse
    (licencias libres). Aun así, casi todo lo que devolvió para escandinavo,
    bohemio y mediterráneo no eran interiores de ese estilo (pabellones que
    parecen generados por IA, portadas de discos, relieves). Contando solo
    fotos revisadas a mano con etiqueta fiable, **large/14 acierta 6/7**
    (rústico 2/2, moderno 2/2, minimalista 1/2, clásico 1/1) y, con el umbral
    p ≥ 0,5 y margen ≥ 0,2, **sugiere en 6 y acierta las 6**. Las etiquetas de
    no-sugerir funcionan en **10/10** casos que no son un estilo (6 exteriores,
    2 habitaciones vacías, portadas de discos, relieve de cerca).
    **Siguen sin validar con fotos buenas: escandinavo, bohemio y
    mediterráneo** (industrial solo en ronda 1, cuando las "industriales"
    resultaron ser fachadas de lofts).
  - **Integrada (2026-09-27):** `server/style.py` + `POST /api/style` (CLIP
    large/14 en el servicio, umbral 0,5 / 0,2, etiquetas de no-sugerir vacía /
    objeto / exterior); en la interfaz, chip "Parece: X ▾" editable sobre la
    foto, nota "detectado automáticamente", y 2–3 estilos de destino marcados
    como "sugerido" (nunca seleccionados solos); si no hay estilo claro, se
    explica por qué y se puede indicar a mano; sin consentimiento no se envía
    nada. Verificado: 13 tests nuevos (70 en total); navegador → servidor real
    (CLIP simulado de forma determinista) a 390 y 1440 px: estilo claro,
    corrección manual, "sin estilo claro", habitación vacía, foto dudosa,
    servicio sin `/api/style` (404), generación con un estilo sugerido, sin
    errores de consola; regresión de zonas, foto entera y 7 vistas. Código de
    producción con CLIP real en GitHub Actions: `validation/results_style_server/`.
    Resultado con CLIP real (`validation/results_style_server/report.md`):
    **12/12 correctos, 0 sugerencias incorrectas** (5 estilos acertados; 4
    exteriores, 2 vacías y 1 dudosa sin sugerencia y con su motivo).
  - **Medición de variantes con el modelo real (2026-09-27, rama
    `claude/variantes-calidad`, `validation/results_variants/`).** Con el
    token de Juan (secreto `HF_TOKEN` de GitHub):
    - **`stabilityai/stable-diffusion-xl-base-1.0` (el `HF_MODEL` por defecto
      de `server/app.py`) NO lo sirve ningún proveedor para image-to-image**:
      con la configuración por defecto, la función fallaría con
      `model_unsupported`. Sí están servidos `black-forest-labs/FLUX.1-Kontext-dev`
      (fal-ai, replicate, wavespeed) y `Qwen/Qwen-Image-Edit` (fal-ai,
      wavespeed). Licencias a revisar antes de elegir: FLUX.1 Kontext [dev]
      tiene licencia no comercial para los pesos; Qwen-Image-Edit es Apache-2.0.
    - **El crédito gratuito se agotó a las 6 generaciones** (HTTP 402 →
      `quota_exhausted`, gestionado como estaba previsto). Con 2-3 variantes
      por petición, cada visualización costaría 2-3 veces más.
    - Latencia (1 foto, FLUX Kontext): 1 variante 45 s; 2 en paralelo 28 s
      en total → en paralelo no se suma el tiempo.
    - Puntuador (LAION + realismo CLIP): de 3 variantes muy distintas (una casi
      sin cambios, una reforma nórdica completa, una intermedia) eligió la
      reforma completa (0,873 frente a 0,786/0,775). La variante "sin cambios"
      puntuó casi igual que el original (0,786 frente a 0,782): el puntuador
      no detecta que el modelo no hizo nada → hace falta una señal de "cambio
      respecto al original" además de la estética.
  - **Filtro de calidad implementado (2026-09-27)**, a la espera de recalibrar
    con crédito. Servidor: `variants` (1–3) en `/api/renovate`, generación en
    paralelo, puntuador `quality.py` (LAION + realismo CLIP + cambio respecto
    al original, con zonas medido en el recorte de la zona), descartes
    (nota < 0,5; cambio < 0,11, provisional), un reintento si caen todas, la
    mejor disponible con aviso, y fallos parciales tolerados. Modelo por
    defecto cambiado a `Qwen/Qwen-Image-Edit` (SDXL no está servido).
    Interfaz: pide 2 versiones, espera "Generando 2 versiones…", muestra la
    elegida con "Ver otras versiones", descartadas con su motivo y aviso de
    calidad baja. Calibración sin crédito: 30/30 fallos simulados por debajo
    de su original. Verificado: 88 tests; navegador → servidor real con
    generación simulada (2 versiones, elegir otra, guardar, calidad baja,
    servidor antiguo que responde JPEG, zonas intactas fuera de la máscara).
    Se detectó y corrigió en la prueba de zonas que medir el cambio sobre la
    imagen entera marcaba "sin cambios" todo cambio de zona (y reintentaba,
    duplicando coste). **Pendiente con crédito:** la medición completa
    (2 frente a 3 versiones en 5 fotos), recalibrar `QUALITY_MIN_CHANGE`
    (sobre todo en modo zonas) y medir Qwen-Image-Edit.
  - **En cola, en este orden:** (1) filtro de calidad con varias variantes
    (medir primero con 2); (2) investigación de reconstrucción 3D de
    habitaciones a partir de fotos (una foto vs. varias/vídeo; licencia,
    cómputo, formato y visor web, madurez, especialización en interiores;
    probar 2-3 con fotos reales; tabla y recomendación para la Fase 0 del
    recorrido virtual). Aviso: este entorno no tiene GPU; las pruebas irían
    por GitHub Actions (CPU) o Spaces públicos.

- **Validación de la segmentación (2026-09-27), hecha en GitHub Actions**
  (`server/validation/`, workflow `validate-segmentation.yml`, rama
  `claude/validacion-segmentacion`; el entorno no llega a huggingface.co).
  SegFormer-b0 ADE20K sobre 10 fotos reales de pisos de Wikimedia Commons
  (licencias libres, atribución en `server/validation/results/report.md`):
  - **Pared, suelo y techo: fiables** en las 10 (confianza media 0,73–0,98),
    también con poca luz (salón vacío oscuro, salón al atardecer).
  - **Mobiliario: aceptable pero con bordes flojos** (confianza 0,48–0,86):
    armarios blancos sobre pared blanca se confunden con pared, la base de
    una isla de cocina sale como pared, unas puertas dobles como mobiliario.
  - **Espejos y cristales: problemáticos** (reflejos clasificados como
    ventana; mampara de ducha como ventana/puerta en la ronda 1). El espejo
    ya se excluye de las zonas.
  - Ronda 1 descartada como muestra (la búsqueda trajo cuadros de museo y
    exteriores); ronda 2 filtra por EXIF de cámara y descarta exteriores.
  - Sin probar aún: buhardillas/techos inclinados.
  - Conclusión: sirve como punto de partida si el usuario **ve y puede
    corregir** la zona antes de generar; no como verdad absoluta.
  - **Ronda 3 (b0 vs b2 vs b4, mismas 10 fotos,
    `server/validation/results_compare/`):** confianza media en mobiliario
    0,69 → 0,83 → 0,86; ventana/puerta 0,78 → 0,87 → 0,89; pared/suelo/techo
    ya altas y suben algo. Tiempo en CPU de 2 núcleos: 0,9 s → 2,7 s → 3,2 s
    por foto. b2/b4 arreglan los armarios blancos sobre pared blanca y las
    puertas; la base blanca de la isla de cocina sigue saliendo como pared en
    los tres. **Recomendación: b4** (mejor en todo por +0,5 s respecto a b2;
    la segmentación se hace una vez por foto), ejecutado dentro del propio
    servicio (sin depender de que un proveedor de HF sirva el modelo y sin
    enviar la foto a otro tercero para segmentar).
- **Segmentación por zonas — IMPLEMENTADA (2026-09-27)** tras la validación.
  Servidor: `server/segmentation.py` (SegFormer-b4 en CPU, zonas, composición
  con máscara), `POST /api/segment` y `mask`/`zones` en `/api/renovate`.
  Interfaz (`ai-renovation.js`): consentimiento antes de detectar, "Solo
  algunas zonas" / "Toda la foto", foto con la selección en verde, tocar zona
  o botones por zona (con %), pincel ＋/－, "Quitar ajustes", resumen de lo que
  se modificará, y si la detección falla se pasa a "Toda la foto" con el
  motivo visible. Verificado: 57 tests `pytest` (composición exacta fuera de
  la máscara, varias zonas, máscaras inválidas/vacías/de otro tamaño, límites
  y fallos del modelo); código de producción con SegFormer-b4 real en
  GitHub Actions sobre 6 fotos (`validation/results_server/`); navegador real
  → servidor real (segmentación simulada con zonas conocidas, generación con
  endpoint local): lo no seleccionado queda intacto (diferencia 0), lo borrado
  con pincel también, varias zonas, foto nueva reinicia, fallo → toda la foto,
  sin errores de consola ni scroll horizontal a 390 y 1440 px; regresión de
  las 7 vistas y del flujo de foto entera.
  Pendiente: probar en un despliegue real (Space) y con buhardillas; el
  endpoint de segmentación no tiene autenticación (límite por IP y
  concurrencia), como el resto del servicio.
- (Histórico) **Segmentación por zonas (pared/suelo/techo/mobiliario) — EN PAUSA hasta
  validar con fotos reales (decisión de Juan, 2026-09-27).** Orden acordado:
  1) validar la segmentación con 5–10 fotos reales, 2) solo entonces servidor
  + interfaz. Bloqueos en la sesión en que se pidió: huggingface.co bloqueado
  por la política de red del entorno, sin `HF_TOKEN`, sin fotos reales.
  Para retomarlo: permitir `huggingface.co` y `router.huggingface.co` en el
  entorno, `HF_TOKEN` como variable de entorno, y fotos en
  `server/validation/fotos/` (mejor fotos con licencia libre: lo que entra en
  git queda en el historial).
  Correcciones al encargo: la fase 1 es img2img (ControlNet no está
  implementado); `runwayml/stable-diffusion-inpainting` ya no existe (espejo:
  `stable-diffusion-v1-5/stable-diffusion-inpainting`); `InferenceClient` no
  tiene tarea de inpainting con máscara.
  Diseño propuesto: segmentación con `nvidia/segformer-b0-finetuned-ade-512-512`
  (`InferenceClient.image_segmentation`), clases ADE20K agrupadas en zonas
  (pared; suelo; techo; ventana/puerta; mobiliario = cama, sofá, mesa, silla,
  armario…), calculada **una vez al subir la foto** y devuelta al navegador
  (el servidor no la guarda); el navegador envía las zonas elegidas con la
  petición de generación; el servidor genera y **compone el resultado solo
  dentro de la máscara** (borde suavizado), de modo que fuera de ella la foto
  queda idéntica píxel a píxel aunque el proveedor no sepa hacer inpainting.

- Desplegar `server/` como Space, poner `HF_TOKEN` como secreto, elegir un
  `HF_MODEL` que `check_model.py` confirme, y poner la URL en `index.html`.
- Revisar la política de retención del proveedor que sirva el modelo
  (fal-ai, Replicate…) y reflejarla en el aviso de privacidad.
- El crédito gratuito de HF da para muy pocas imágenes: para usuarios reales,
  cuenta con facturación y tope de gasto.
- Fase 2: ControlNet (depth/canny) en un Inference Endpoint o Space con GPU
  para bloquear de verdad la geometría.


- **Auditoría del repositorio y correcciones (2026-09-27).** `homeai-claude` es
  el repositorio principal (`JuanCopado/HOMEAI` es una versión anterior, sin las
  funciones de IA local ni el Digital Twin). Hallazgo principal: la subida inicial
  no incluyó `assets/`, `tests/` ni `.openai/`. Corregido lo que se podía corregir
  sin esos archivos:
  - `npm test` pasa por `run-tests.mjs`: ejecuta `planner-geometry.test.cjs`
    (30 aserciones) aunque falte `tests/design-state.test.mjs`, y avisa de lo que
    falta (antes abortaba sin ejecutar nada).
  - `build.mjs` falla con un mensaje claro si falta `assets/`.
  - `sw.js` precachea archivo a archivo (`Promise.allSettled`) en vez de
    `cache.addAll`: un archivo ausente ya no deja la PWA sin modo offline. Caché
    `homeai-studio-v19`. Verificado con Playwright: 28 archivos en caché (antes 0
    con `assets/` ausente), 7 vistas × 390/921/1440 px sin errores de consola.
  - Tesseract fijado a `tesseract.js@5.1.1` (antes `@5`, versión flotante).
  - 4 `catch(e)` sin usar en `app.js` → `catch` (quedan 3 avisos de lint).
  - CI mínimo en `.github/workflows/ci.yml` (`lint:js` + `test`).
  - Recuento de archivos corregido en `AGENTS.md`, `PROJECT.md` y
    `eslint.config.mjs` (13 JS / 11 CSS).

## Pendiente de la auditoría (2026-09-27)

- ~~Subir `assets/`, `tests/` y `.openai/hosting.json`~~ **Resuelto**: Juan subió
  `assets/` (7 imágenes) y `tests/design-state.test.mjs`; `npm test` completo pasa
  (design-state + 30 aserciones de geometría), `node build.mjs` genera `dist/` y el
  barrido Playwright sobre `dist/` (7 vistas × 390/921/1440 px) da 0 errores de
  consola, 0 peticiones fallidas y 35/35 archivos precacheados por el SW.
  `.openai/hosting.json` no apareció en la copia local: se **reconstruyó** con lo
  único documentado (`{"static":{"directory":"dist"}}`); si el hosting de ChatGPT
  necesita más campos, sustituirlo por el original. `assets/tipo-a.png` no hace
  falta: `app.js` solo lo usa para migrar proyectos antiguos que lo referencian.
- SRI para Tesseract: hash candidato calculado del tarball npm 5.1.1
  (`sha384-GJqSu7vueQ9qN0E9yLPb3Wtpd7OrgK8KmYzC8T1IysG1bcvxvIO4qtYR/D3A991F`),
  no aplicado porque el proxy de este entorno bloquea jsdelivr y no se pudo
  comprobar que coincide byte a byte. Tampoco hay CSP en `index.html`: añadirla
  requiere probar OCR, WebLLM y diffusers (workers/wasm/blob) en un navegador real.
- `AGENTS.md` referencia `.claude/agents/*.md`, que no existen en el repositorio.
- `JuanCopado/HOMEAI`: `BACKUP_STATUS.md`/`docs/project-manifest.json` dicen que
  no hay código fuente (ya lo hay) y su `CURRENT_STATE.md` no corresponde a este
  proyecto; decidir si se archiva o se sincroniza con este repositorio.

- **Opciones gratuitas/locales de IA (2026-09-26): implementadas dos de las
  tres, la tercera bloqueada por seguridad del entorno de desarrollo — sin
  comprometer proveedores de pago.** Juan pidió explícitamente implementar
  las alternativas gratuitas de `PROVEEDORES_IA.md` ("las tres a la vez").
  Resultado, honesto sobre lo que se pudo y lo que no:
  - **Orquestador de lenguaje natural (`ai-orchestrator.js`/`.css`)**:
    implementado con WebLLM (`@mlc-ai/web-llm`, modelo
    `Llama-3.2-3B-Instruct-q4f16_1-MLC`), cargado bajo demanda desde CDN
    exactamente como `loadTesseract()` — nada se descarga hasta que el
    usuario pulsa el botón en la vista de Presupuesto. Solo lee `project`
    (rooms/costs/style) como contexto; su salida es texto de solo lectura,
    nunca escribe presupuesto ni geometría. Degrada con gracia sin WebGPU o
    si falla la carga. **Verificado con Playwright antes del corte de
    herramientas descrito abajo**: la tarjeta se inyecta en el sitio
    correcto, un envío vacío da toast sin romper nada, y se confirmó por
    separado que el módulo de `@mlc-ai/web-llm` sí carga desde el CDN y
    expone `CreateMLCEngine` tal como se usa en el código.
  - **Generación de interiores (`ai-interior-preview.js`/`.css`)**:
    implementado con `@aislamov/diffusers.js` (Stable Diffusion 2.1 base,
    ONNX+WebGPU, MIT), en la vista de Diseño. **Alcance reducido a propósito
    y declarado en el propio código**: genera una imagen de inspiración a
    partir de texto (texto→imagen), NO parte de la foto real del usuario ni
    la modifica — la vía correcta para eso sería imagen→imagen o ControlNet,
    cuya forma exacta de API en esta librería no se pudo verificar de forma
    fiable (la documentación pública no la cubre y las herramientas de
    búsqueda de esta sesión llegaron a su límite antes de confirmarla). Se
    prefirió no adivinar esa llamada y arriesgarse a algo roto o engañoso.
    La función que interpreta la salida del modelo (`imageResultToUrl()`)
    es deliberadamente defensiva (prueba varias formas conocidas de salida)
    en vez de asumir una sola, por la misma razón.
  - **Detección de planos con un modelo de visión real (ONNX en navegador)**:
    investigado y NO implementado. Existe un modelo real, gratuito y
    usable — `floor-plan-object-detection` (YOLOv8, licencia MIT, pesos
    `best.pt` descargables, detecta exactamente columnas/muros/puertas/
    ventanas/persianas/escaleras) — pero convertirlo a ONNX exige descargar
    y ejecutar ese checkpoint de PyTorch de un repositorio de terceros
    (deserialización de pickle) e instalar el toolchain necesario
    (`ultralytics`/`torch`). El clasificador de seguridad de este entorno
    sandboxed lo bloqueó dos veces como "Code from External" — un riesgo
    real (un `.pt` puede ejecutar código arbitrario al cargarse) que no se
    debe ni se puede rodear desde aquí. Camino exacto documentado en
    `PROVEEDORES_IA.md` para que Juan lo haga en un entorno que él controle
    y entregue solo el `.onnx` resultante, que sí se integraría aquí sin
    problema (es un archivo de datos, no código a ejecutar).
  - **Otros cambios de soporte**: `sw.js` (`FILES`) actualizado para
    precachear los cuatro archivos nuevos, con bump de versión de caché
    (`homeai-studio-v18`) para que los usuarios que ya instalaron la PWA
    reciban la actualización; `eslint.config.mjs` con `budgetTotal` añadido
    a `crossFileGlobals` (usado por `ai-orchestrator.js`).
  - **Verificación completa (retomada tras una interrupción temporal de las
    herramientas de ejecución del agente, ya resuelta)**: `npm run
    lint:js` → 0 errores (se corrigieron 2 reales en
    `ai-interior-preview.js`: `HTMLCanvasElement`/`ImageData` no estaban
    declarados como globals del navegador en `eslint.config.mjs`, y un
    `catch(e)` con variable sin usar); `npm run lint:css` → mismos 70
    errores preexistentes de siempre (los dos CSS nuevos no añaden
    ninguno); `npm test` → sin regresión; `node build.mjs` → los cuatro
    archivos nuevos llegan a `dist/`. Barrido Playwright: las dos tarjetas
    se inyectan en la vista correcta (`#view-budget` y `#view-design`,
    esta última justo después de "Diseños guardados por estancia"), un
    envío vacío en cualquiera de las dos da un toast sin romper nada, y se
    recorrieron las 7 vistas de la app sin un solo error de consola. Se
    confirmó además, por separado, que **ambos módulos cargan de verdad
    desde jsdelivr** y exponen exactamente las funciones que el código
    usa: `@mlc-ai/web-llm` expone `CreateMLCEngine`; `@aislamov/diffusers.js`
    expone `DiffusionPipeline.fromPretrained` — y, dato relevante, **no
    expone ningún `StableDiffusionControlNetPipeline`** en su build actual,
    lo que confirma que la decisión de no implementar imagen→imagen/
    ControlNet en la primera versión (sección de arriba) era la correcta,
    no solo la prudente.

- **Digital Home Twin, fase 3 implementada y verificada: presupuesto conectado
  a los huecos detectados.** Hallazgo honesto primero: la longitud de pared
  que ya usa el presupuesto (`calculateWallLength()`) **no necesitaba
  "descontar" los huecos** — como se calcula sumando solo los segmentos de
  pared que `detectWalls()` encontró, y un hueco es precisamente la ausencia
  de un segmento ahí, la superficie de pintura y la longitud de zócalos ya
  excluían las puertas de forma correcta desde el principio (no había nada
  que arreglar). Lo que sí faltaba y sí aporta valor real: una partida propia
  para las aberturas. `costQuantity()` añade `qtyType:'openings'` →
  `wallOpenings.length`; `freshProject()` añade una fila por defecto "Puertas
  y aberturas detectadas" (unidad, cantidad = huecos detectados) — solo para
  proyectos nuevos, sin tocar los ya guardados. **Verificado**: `npm run
  lint`/`npm test`/`node build.mjs` limpios, un script Playwright confirma que
  un proyecto nuevo con un plano con una puerta detectada calcula la partida
  en 1 unidad, y se repitió el barrido completo de las 7 vistas más los tres
  scripts de verificación de las fases 1 y 2 — sin regresiones.
  - **Nota honesta sobre lo que sigue** (no se avanzó más, ver "Pendiente"):
    las fases que quedan del plan de Juan (visión real sobre fotos/vídeo,
    generación de interiores por lenguaje natural, un orquestador que
    entienda frases libres como "tengo 25.000€...") necesitan todas un
    LLM/API de visión externo — proveedor, credenciales y coste que no
    existen en este entorno y que no se deben comprometer sin que Juan lo
    apruebe explícitamente (implica dinero real y una promesa de privacidad
    que hoy dice "nada sale del dispositivo"). Un recomendador basado en
    reglas fijas (sin LLM) sería técnicamente posible, pero es una función
    nueva de tamaño considerable (formulario de presupuesto/familia/
    preferencias, generación de 3 alternativas) — no una mejora incremental
    sobre código existente como las tres fases anteriores, así que no se
    empezó sin que Juan la revise primero.
- **Digital Home Twin, fase 2 implementada y verificada: detección de huecos
  (puertas/ventanas).** `planner-geometry.js` añade `detectOpenings()`: dentro
  de una misma línea de pared ya detectada, un hueco de anchura plausible
  (0.5–1.6 m por defecto, configurable) entre dos segmentos es candidato a
  apertura. Es puramente geométrico (sin canvas, sin ML) y **deliberadamente
  no distingue puerta de ventana** — eso necesitaría leer el símbolo real del
  plano (arco de puerta vs. líneas paralelas) o visión de verdad, así que se
  devuelve genéricamente como `kind:'opening'` con su propio `confidence`,
  para no prometer más precisión de la que hay (mismo criterio de honestidad
  que ya se aplicó al etiquetar `detectWalls()`/`analyzeLines()` como
  heurísticas, no como IA). En `app.js`, `detectWallOpenings()` (llamada desde
  `detectWalls()` y desde los dos manejadores de edición manual de muros)
  guarda el resultado en `wallOpenings`; `renderWallEditor()` lo dibuja como
  una línea discontinua morada sobre el hueco detectado, distinta de las
  paredes (naranja detectadas, verde manuales). **Verificado con evidencia**:
  6 aserciones nuevas en `planner-geometry.test.cjs` (hueco plausible
  detectado, hueco de ruido descartado, hueco demasiado grande descartado) —
  30 en total, todas pasan; `npm run lint` en 0 errores; `node build.mjs`; un
  script Playwright con un plano sintético con una puerta real de 0.8 m en un
  muro divisorio confirma que se detecta exactamente ese hueco (ancho 0.81 m,
  confianza 0.74) sin errores de consola; y se repitieron los dos scripts de
  verificación de la fase 1 (enlace paredes-habitaciones, estático y
  reactivo) más el barrido de las 7 vistas — mismos resultados limpios que
  antes, sin regresiones.
- **Digital Home Twin, fase 1 implementada y verificada: enlazar paredes a
  habitaciones.** Antes, `project.rooms` (medidas) y `wallSegments` (paredes
  detectadas por `detectWalls()`) eran dos estructuras desconectadas — el 3D
  dibujaba las paredes reales pero colocaba los nombres de habitación en una
  cuadrícula arbitraria. Ahora:
  - `planner-geometry.js` (pura, testeada en Node como el resto del archivo)
    añade `computeRoomRegions()` (deriva regiones libres/candidatas a
    habitación a partir de los segmentos de pared vía rasterizado en grid +
    flood-fill, sin canvas y sin ML) y `matchRoomsToRegions()` (empareja cada
    `project.room` con la región de área más parecida, con `confidence` según
    lo ajustado que sea el emparejamiento).
  - `app.js` añade `linkRoomsToWalls()`, llamada desde `detectWalls()` y desde
    los dos manejadores de edición manual de muros. Marca cada resultado como
    `room.wallRegion = {..., source:'vision-heuristic', confidence, verified:false}`
    — generaliza el mismo patrón `verified`/`source` que `project.rooms` ya
    usaba para el OCR. Si el enlace falla o no hay plano/habitaciones, no
    rompe nada: se borra `wallRegion` y el render cae al comportamiento
    anterior (cuadrícula).
  - `renderModel()` usa `room.wallRegion.cx/cy` para colocar el nombre de cada
    habitación en su posición real cuando existe; si no, usa la cuadrícula de
    siempre (fallback intacto, cero regresión para proyectos sin plano).
  - **Verificado con evidencia**: `npm test` (25 aserciones en
    `planner-geometry.test.cjs`, incluida la geometría nueva, más los tests
    existentes de `design-state.test.mjs`), `npm run lint` (0 errores, mismos
    70 de CSS y mismos warnings de siempre), `node build.mjs`, un script
    Playwright con un plano sintético de 2 habitaciones que confirma que cada
    una liga con su mitad real del plano (sin excepciones ni errores de
    consola), y un barrido de regresión de las 7 vistas + interacciones
    (0 errores de consola, 0 peticiones fallidas — igual que antes del
    cambio).
  - **Cerrado (2026-09-26, a petición de Juan de no dejarlo fuera)**: el
    enlace ahora también se recalcula al editar el ancho/largo de una
    habitación (`renderRooms()`), al confirmar su medida ("Confirmar"), al
    añadir una estancia (`addRoom()`/`createDesignRoom()`), al eliminarla
    (`data-remove-room`) y al fusionar medidas nuevas del OCR
    (`analyzePlan()`) — no solo tras detectar o editar paredes. Se hizo con
    cuidado de **no** forzar además un `renderModel()` nuevo en los sitios
    donde antes no lo había (`createDesignRoom`, `addRoom`, "Confirmar",
    `analyzePlan`): el primer intento sí lo añadía y rompió
    `tests/design-state.test.mjs` (su entorno de prueba simula el DOM con un
    canvas sin `getBoundingClientRect`, y ese test llama a `createDesignRoom()`
    directamente) — corregido dejando solo `linkRoomsToWalls()` en esos
    puntos; la posición se refresca en el próximo render natural (cambiar de
    vista, redimensionar, o los puntos que ya llamaban a `renderModel()` antes
    de este cambio, como borrar una habitación). Reverificado con Playwright:
    dos habitaciones sin medir empiezan con enlace de baja confianza (0.25,
    emparejamiento por descarte) y, tras escribir sus medidas reales sin
    volver a cargar el plano, `linkRoomsToWalls()` las reubica correctamente
    en su mitad real (confianza ~0.47/0.46, igual que si la medida hubiera
    estado desde el principio) — sin errores de consola. `npm test`,
    `npm run lint` y el barrido de las 7 vistas siguen limpios.
  - Detalle completo de diseño en `DIGITAL_TWIN_ARCHITECTURE.md`.
- **Diseño de arquitectura "Digital Home Twin"** (`DIGITAL_TWIN_ARCHITECTURE.md`,
  solo diseño, sin código de producto): responde a la visión de Juan de un
  módulo de visión + interpretación de planos + gemelo digital + 3D +
  generación de interiores + presupuesto + recomendador + agentes internos.
  Hallazgo clave que fundamenta el diseño: `project.rooms` (medidas) y
  `wallSegments` (paredes detectadas por `detectWalls()`) son hoy **dos
  estructuras desconectadas** — el 3D dibuja las paredes reales pero coloca
  los nombres de habitación en una cuadrícula arbitraria, no en su posición
  real. El documento propone `project.twin` (aditivo, retrocompatible),
  generaliza a paredes/puertas/ventanas el patrón `verified`/`source` que
  `project.rooms` ya usa, separa capa técnica (geometría verificada) de capa
  generativa (estilo/decoración) para que la IA nunca pise la geometría en
  silencio, y da una hoja de ruta en fases marcando explícitamente cuál es la
  única que exige backend/coste externo (visión real sobre fotos/vídeo). Nada
  de esto se ha implementado todavía — es la base para decidir por dónde
  empezar.
- **3 bugs corregidos** (auditoría inicial, sesión 2026-09-25/26):
  1. "Probar con un ejemplo" en el estudio fotográfico no cargaba la imagen de
     muestra (`photo-studio.js`, validación de tipo MIME del blob).
  2. Moneda por defecto del presupuesto fija en COP para cualquier usuario
     (`app.js`, ahora `defaultCurrency()` según región del navegador).
  3. Barra de calibración de escala en Plano se veía apretada/rota entre 600 y
     1200px de ancho (`workspace-v17.css`, `flex-wrap` solo estaba activo bajo
     600px).
  - Detalle completo con causa/arreglo/verificación en `CHANGELOG_CLAUDE.md`.
- **Auditoría de las 9 hojas de CSS**: documentada en `CSS_AUDIT.md`. Conclusión:
  el patrón de "capas por versión" es intencional; no se fusionaron a ciegas. Se
  hizo un barrido visual (Playwright, 7 vistas × 3 anchos) que no encontró más
  bugs de layout aparte del ya corregido.
- **ESLint + Stylelint añadidos** (`eslint.config.mjs`, `.stylelintrc.json`,
  scripts `npm run lint:js` / `lint:css` / `lint` / `test`). Configurados a medida
  del proyecto (globals cross-file explícitas, reglas de CSS centradas en errores
  reales, no en formato). Ya encontraron un bug real al ejecutarse por primera
  vez: `font:600 15px/1.3 inherit` en `workspace-v17.css` es un atajo `font`
  inválido (el navegador lo descartaba entero); corregido separando en
  `font-weight`/`font-size`/`line-height`.
- **Restaurar copia de seguridad (.JSON)**: ya existía exportar el proyecto a
  JSON pero no había forma de restaurarlo. Añadido botón en el modal de Exportar
  (`app.js`, función `importProjectFromFile`), con validación de formato y
  confirmación explícita antes de sustituir el proyecto activo. Verificado con
  Playwright (exportar → mutar → restaurar → vuelve al estado original;
  un archivo inválido no toca el proyecto).
- Todo lo anterior está comiteado en el repo local (ver `git log` para el hash
  exacto; dos commits: importación del código real + fixes, y esta segunda
  tanda de auditoría/lint/backup).
- Sistema multi-agente creado: este archivo, `AGENTS.md`, `PROJECT.md` y los 6
  agentes en `.claude/agents/`.

## Hallazgos de la auditoría técnica y funcional (2026-09-26)

Auditoría completa (no refactor) usando los 4 subagentes (architect, ux-ui,
ai-engineer, security) más ejecución directa: `npm test` (pasa), `npm run
lint` (0 errores JS, los mismos 70 errores CSS ya conocidos y documentados),
`node build.mjs`, barrido Playwright de consola/red en las 7 vistas (0 errores
de consola, 0 peticiones fallidas, 0 respuestas 4xx/5xx), y revisión directa de
`manifest.webmanifest`, `sw.js`, `index.html`. Detalle completo en el doc
"HomeAI — Auditoría y plan de mejora" (Claude Docs). Resumen aquí:

- **Seguridad (prioridad alta, único hallazgo nuevo con riesgo real)**: el flujo
  de restaurar copia de seguridad (`importProjectFromFile` en `app.js`) valida
  forma mínima (`rooms`/`tasks` como arrays) pero no el contenido:
  1. Un JSON restaurado puede traer un documento con `src`/`href` tipo
     `javascript:...`, que `renderDocs()` vuelca a `innerHTML` — XSS si el
     usuario abre un backup de origen no confiable.
  2. La validación de tipos dentro de cada objeto (no solo la forma del array)
     es insuficiente: un backup malformado puede corromper `localStorage` antes
     de que la UI pueda rechazarlo (efecto "auto-DoS").
  Ambos son arreglos acotados en `importProjectFromFile`/`renderDocs`, no
  requieren tocar arquitectura.
- **Arquitectura y calidad de código**: confirmado que la cadena de "monkey
  patch" sobre `renderDesign`/`renderFinishList`/`goView`/`renderOverview`
  (4/3/2/1 reasignaciones respectivamente, ver `PROJECT.md`) sigue funcionando
  hoy sin roturas, pero no hay lint ni test que la proteja si un archivo nuevo
  rompe el orden de carga en `index.html`. Deuda de los 70 selectores
  duplicados en `styles.css` sigue igual (ver abajo). Código muerto confirmado
  (`on()` en `app.js`) y una variable sin usar en `exportObj()` — limpieza
  trivial, sin riesgo.
- **UX, accesibilidad y SEO**: PWA con un solo icono SVG "any maskable" —
  funciona en Android pero iOS/Safari no lee el manifest para "Añadir a
  pantalla de inicio" y necesita un `apple-touch-icon` PNG explícito (defecto
  real, no teórico, arreglo acotado). Sin meta `og:*` ni `canonical`. Sin
  auditoría de accesibilidad dedicada más allá del barrido responsive
  existente (pendiente revisar contraste, `tabindex`, etiquetas de formulario).
- **PWA/rendimiento**: `sw.js` precachea 30 archivos de forma atómica
  (`cache.addAll`) — si uno falla, falla la instalación completa del Service
  Worker; incluye ~2MB de imágenes de ejemplo no usadas en el flujo real.
- **Oportunidades de IA (evaluación honesta)**: hoy "IA" en HomeAI es 100%
  local — OCR con Tesseract.js (esto sí es ML real), detección de muros por
  heurística de contraste de píxeles (no es un modelo, aunque se presente como
  "IA" en la UI) y maqueta 3D por extrusión conceptual (tampoco es un modelo).
  Margen real de mejora a corto plazo: tolerancia del parser de OCR (regex
  única, frágil) y separar en la UI lo que es heurística determinista de lo que
  sería IA real, para no sobre-prometer. Una función como "plano → propuesta de
  reforma 3D generada" es un proyecto grande y costoso (modelo de visión +
  posible servicio remoto con coste/latencia), no una mejora incremental —
  requiere decisión de producto explícita antes de empezar.
- **Nada roto**: no se encontraron regresiones de las últimas dos sesiones;
  `npm test`, `npm run lint` y el barrido de consola están limpios salvo la
  deuda ya conocida.

## Deuda conocida (documentada, no resuelta)

- `styles.css` tiene 70 selectores duplicados dentro del propio archivo
  (detectados por `stylelint`, listados en `CSS_AUDIT.md`). No se tocaron por el
  riesgo de editar a ciegas un archivo de 83KB en una sola línea sin poder
  confirmar visualmente cuál versión es la vigente en cada caso.
- No hay CI configurado; toda la verificación (`npm test`, `npm run lint`,
  barrido visual con Playwright) se hace manualmente en cada sesión.
- No se ha hecho una auditoría de accesibilidad dedicada (solo lo que ya cubre
  el barrido visual/responsive).
- La detección de muros y la maqueta 3D son heurísticas simples (contraste de
  píxeles + extrusión 2D), no un modelo de visión ni un motor 3D real — ver
  `PROJECT.md`. Cualquier mejora real de precisión es una tarea grande para
  AI Engineer + Architect juntos, no un ajuste rápido.

## Pendiente

- **Digital Home Twin — hasta dónde se pudo llegar en local (2026-09-26)** (ver
  `DIGITAL_TWIN_ARCHITECTURE.md`): ligar paredes a habitaciones, detectar
  huecos y conectarlos al presupuesto ya están hechos y verificados (ver
  "Hecho") — es todo lo que el plan de 8 puntos de Juan permite avanzar sin
  introducir un backend ni depender de un proveedor externo de pago. Lo que
  queda **no es un siguiente paso técnico de esta misma naturaleza**, sino
  una decisión de producto real que solo Juan puede tomar:
  1. **Visión real** (fotos/vídeo/croquis/capturas inmobiliarias), **generación
     de interiores por lenguaje natural** y un **orquestador que entienda
     frases libres** ("tengo 25.000€, somos 4...") necesitan todas un LLM o
     una API de visión externa — proveedor, credenciales y coste real que hoy
     no existen en el proyecto ni en este entorno, y que cambiarían la
     promesa actual del `README.md` ("nada sale del dispositivo"). No se
     implementó nada de esto ni se eligió proveedor por cuenta propia.
  2. Distinguir puerta de ventana de verdad necesitaría lo mismo (leer el
     símbolo del plano o visión real) — por eso `kind` sigue siendo
     `'opening'` genérico.
  3. Un **recomendador por reglas fijas** (presupuesto + familia +
     preferencias → 3 alternativas) sí sería técnicamente posible sin LLM,
     pero es una función nueva de tamaño considerable (formulario nuevo,
     generación de alternativas) y no una mejora incremental sobre código
     existente como las tres fases ya hechas — se dejó documentada aquí en
     vez de construirla sin que Juan la revise primero, para no convertir un
     cambio incremental en la reconstrucción que pidió evitar desde el
     principio.
- **Subir estos cambios a GitHub** (`https://github.com/JuanCopado/HOMEAI.git`):
  tiene que hacerlo Juan manualmente (`git remote add origin ...` + `git push`),
  ningún agente puede hacerlo desde este entorno (sin credenciales de git que
  funcionen aquí).
- **Siguiente trabajo recomendado (plan incremental, pendiente de que Juan dé
  luz verde a cuál atacar primero)** — orden por impacto/dependencia, no por
  puntuación:
  1. **Sin dependencias, bajo riesgo — se puede hacer ya**: arreglar las dos
     vulnerabilidades de seguridad en restaurar backup (validar/rechazar
     esquema `javascript:` en `src`/`href` antes de `innerHTML`, y endurecer la
     validación de tipos por objeto, no solo la forma del array); añadir
     `apple-touch-icon` PNG para iOS; limpiar código muerto (`on()` en
     `app.js`, variable sin usar en `exportObj()`).
  2. **Requiere red de seguridad primero (barrido visual + test manual antes y
     después, no tocar a ciegas)**: separar la precarga atómica del Service
     Worker de las imágenes de ejemplo no usadas; dar más tolerancia al parser
     de OCR de medidas; revisar contraste/`tabindex`/etiquetas de formulario
     como primera pasada real de accesibilidad; considerar (sin decidir aún)
     empezar a fusionar los 70 selectores duplicados de `styles.css`, archivo
     por archivo, con verificación visual en cada paso.
  3. **Decisión de producto, no técnica**: si merece la pena separar en la UI
     lo que hoy se llama "IA" (heurísticas locales deterministas) de lo que
     sería IA real, para no sobre-prometer; y si se quiere explorar una función
     tipo "plano → propuesta de reforma 3D" — grande, cara, con dependencia de
     un modelo de visión y posiblemente un servicio remoto (coste/latencia) —
     antes de comprometerse hace falta que Juan decida alcance y presupuesto.
- **Investigación de proveedores/precios de IA (2026-09-26)**: Juan pidió
  buscar alternativas de proveedores y precios para implementar las fases que
  faltan (visión real, generación de interiores, orquestador de lenguaje
  natural), incluyendo explícitamente opciones gratuitas y "hazlo tú con
  esfuerzo", no solo APIs comerciales. Resultado documentado en
  `PROVEEDORES_IA.md`: tabla comparativa de precios reales (Anthropic, Google
  Gemini, OpenAI, AWS Rekognition, Azure AI Vision, CubiCasa, Roboflow,
  Stability AI, Replicate) frente a alternativas open-source/autoalojadas
  (DeepFloorplan, YOLOv8 sobre floor-plan-object-detection, Stable Diffusion +
  ControlNet local, Ollama con un LLM local). Hallazgo más importante, que no
  estaba planteado antes de investigar: como HomeAI no tiene backend hoy,
  cualquier proveedor de pago exige decidir primero dónde vive la clave de
  API (backend propio nuevo, clave del propio usuario en su navegador, o
  quedarse en opciones 100% locales) — es una decisión de arquitectura previa
  a "qué proveedor", y sigue sin resolver. No se ha implementado ni
  comprometido ningún proveedor; es solo la base de datos para que Juan
  decida con cifras reales delante.
- Nada más en cola por ahora — la próxima tarea la decide el coordinador según lo
  que pida Juan, releyendo este archivo primero.
