# PROVEEDORES_IA.md — alternativas para las fases que necesitan IA externa

> Documento de **investigación de proveedores**, no de implementación. Responde
> al encargo de Juan: "busca alternativas proveedores precios, para
> implementar el proyecto" + "hay herramientas gratuitas y otras que puedes
> hacer con algún esfuerzo". Cubre las tres capacidades que
> `DIGITAL_TWIN_ARCHITECTURE.md` identificó como las únicas que de verdad
> necesitan un modelo externo (fase 4 en adelante): visión real sobre
> fotos/vídeo/planos, generación de interiores, y un LLM para el orquestador
> de lenguaje natural. No se ha escrito ni un contrato de API en el código —
> esto es solo la base para que Juan decida. Fecha: 2026-09-26.

## 0. Un problema de arquitectura que hay que resolver antes de elegir proveedor

HomeAI hoy es una app estática sin backend: todo corre en el navegador del
usuario, y el `README.md` promete "nada sale de tu dispositivo". Cualquiera
de las opciones de pago de abajo se llama con una API key — y una API key
puesta en `app.js` queda visible para cualquiera que abra las herramientas de
desarrollador del navegador. Esto no es un detalle menor: significa que **la
primera decisión no es "qué proveedor", sino "quién guarda la clave"**. Las
salidas honestas son tres, y aplican a cualquier proveedor de pago que se
elija de la lista siguiente:

1. **Introducir un backend propio** (aunque sea una función serverless
   mínima) que reciba la petición del navegador, añada la clave del lado del
   servidor y reenvíe la llamada. Es la opción estándar de la industria, pero
   es un cambio de arquitectura real: HomeAI deja de ser "solo estático".
2. **Pedir al usuario su propia API key** y guardarla solo en su navegador
   (`localStorage`), sin que pase por ningún servidor de HomeAI. Mantiene la
   promesa de "nada sale de HomeAI", pero traslada la fricción y el coste a
   cada usuario, y sigue exponiendo su clave a quien tenga acceso a ese
   navegador.
3. **Quedarse en opciones que corren localmente** (sección 4): sin API key,
   sin backend, sin coste por uso — a cambio de que el propio dispositivo del
   usuario tenga que hacer el cómputo, que es pesado para visión/generación de
   imágenes.

Esto no bloquea la investigación de precios que pidió Juan, pero sí cambia la
pregunta: cualquier cifra de "coste por uso" de las secciones 1–3 lleva
implícito, además, el coste de construir y mantener ese backend.

## 1. Visión real (fotos, vídeo, planos escaneados, sketches, anuncios inmobiliarios)

### 1.1 De pago, uso general (visión + lenguaje, no especializado en planos)

| Proveedor | Precio aprox. (sept. 2026) | Notas |
|---|---|---|
| **Anthropic Claude** (Sonnet 5 / Haiku 4.5) | Sonnet 5: \$2/\$10 por millón de tokens (entrada/salida); Haiku 4.5: \$1/\$5 por millón | La imagen se factura como tokens normales (no hay tarifa aparte "por imagen"); una foto de habitación típica ronda 1.000–1.600 tokens según resolución. Sin llamada de función especializada en planos — hay que describirle la tarea en el prompt. |
| **Google Gemini** (línea Flash-Lite) | Desde \$0,25–\$0,30 por millón de tokens de entrada (texto/imagen/vídeo), \$1,50–\$2,50 de salida | Tiene **capa gratuita** con límite de peticiones/día — la más barata de las tres para probar sin coste. |
| **OpenAI** (modelos con visión actuales) | Los modelos de generación de imagen rondan \$2,50–\$5/millón tokens de texto de entrada, \$15–\$30/millón de salida; los modelos de audio/visión en tiempo real desde \$0,80/millón (mini) | GPT-4o ya no aparece en la documentación de precios vigente — la gama ha rotado a modelos más nuevos. |
| **AWS Rekognition** | \$0,001 por imagen (primeras 1M/mes), bajando por volumen; 1.000 imágenes/mes gratis el primer año | Pensado para detección de objetos/etiquetas genéricas, no para planos arquitectónicos ni habitaciones concretas — habría que entrenar `Custom Labels` aparte (coste adicional). |
| **Azure AI Vision** | Tarificación por transacción, similar a Rekognition (consultar calculadora oficial; las cifras exactas varían por región) | Mismo caso que Rekognition: visión genérica, no floor-plan-aware. |

### 1.2 Especializado en planos arquitectónicos

| Proveedor | Qué hace | Precio |
|---|---|---|
| **CubiCasa** | App/servicio que convierte fotos de un plano en 2D/3D vectorizado con medidas, con API disponible | Precios por planes/paquete (2D, 2D+mobiliario, 3D), no publicados como tarifa por API en la página pública — hay que contactar a ventas para el precio de uso programático. Es la opción más cercana a lo que pide el punto 2 de Juan, pero no es autoservicio barato. |
| **Roboflow** | Plataforma para entrenar/desplegar un modelo de visión propio (YOLO, etc.) con tus propias imágenes de planos | Capa gratuita ("Public", sin tarjeta) con créditos limitados/mes; plan "Core" desde ~\$79-\$99/mes con 50 créditos/mes | Aquí el coste real es el **entrenamiento**: hay que etiquetar planos propios (paredes/puertas/ventanas) para que el modelo aprenda esos conceptos — Roboflow da la infraestructura, no el dataset. |

### 1.3 Gratis / open-source (autoalojado, sin llamada externa)

Existen varios proyectos publicados que atacan directamente "detectar
paredes/puertas/ventanas/habitaciones en un plano", el mismo problema que
`detectWalls()` resuelve hoy con heurística de contraste de píxeles:

- **CubiCasa5k** — el dataset público (5.000 planos anotados) que varios de
  estos proyectos usan para entrenar; es la base de datos, no un modelo
  listo para usar.
- **DeepFloorplan** (`zlzeng/DeepFloorplan`, GitHub) — modelo de segmentación
  semántica de planos (habitaciones + paredes), entrenado sobre CubiCasa5k.
  Gratis, pero exige correr un modelo de deep learning (TensorFlow) en algún
  sitio con GPU razonable — no es viable en el navegador del usuario tal cual.
- **floor-plan-room-segmentation** (`ozturkoktay`, GitHub) — U-Net + ResNet
  para clasificar habitaciones/paredes/puertas/ventanas. Mismo perfil: gratis,
  pero necesita servidor con GPU para inferencia razonable.
- **floor-plan-object-detection** (`sanatladkat`, GitHub) — YOLOv8 entrenado
  específicamente para detectar columnas/paredes/puertas/ventanas como cajas
  delimitadoras. Es el más parecido en espíritu a lo que ya hace
  `detectOpenings()`/`computeRoomRegions()` en `planner-geometry.js`, solo que
  con una red neuronal en vez de geometría pura.

**Lectura honesta de esta sección**: "gratis" aquí significa "sin licencia
que pagar", no "sin coste de infraestructura". Ejecutar cualquiera de estos
modelos con una latencia aceptable normalmente pide una GPU (propia o
alquilada por horas en algo como una instancia cloud con GPU), lo cual
reintroduce un coste de servidor aunque no sea una API de pago por token.

## 2. Generación de interiores (imagen generativa: "aplica estilo japandi a este salón")

### 2.1 De pago

| Proveedor | Precio aprox. (sept. 2026) | Notas |
|---|---|---|
| **Stability AI** (API oficial, Stable Image / SD3.5) | Stable Image Core: \$0,03/imagen; SD3.5 Medium: \$0,035; SD3.5 Large Turbo: \$0,04; SD3.5 Large: \$0,065; Stable Image Ultra: \$0,08; operaciones de edición (inpaint, remove-bg, search-and-replace): \$0,05 cada una | El más barato de los "por imagen" con marca reconocida. Sistema de créditos (1 crédito = \$0,01). |
| **Replicate** | Paga por segundo de cómputo del modelo que elijas (no hay tarifa fija única) — un modelo de Stable Diffusion inpainting típico ronda unos pocos centavos por imagen según el hardware asignado | Más flexible (miles de modelos publicados por la comunidad), pero el precio exacto depende de qué modelo concreto se use. |
| **RoomGPT / Reimagine Home** (SaaS de consumo) | Estas son apps ya montadas (no APIs pensadas para integrarse), con sus propios planes de suscripción al usuario final | No son la pieza que HomeAI integraría como API — son la referencia de "qué aspecto final" se busca imitar. |

### 2.2 Gratis / open-source (autoalojado)

- **Stable Diffusion local** (vía `ComfyUI` o `AUTOMATIC1111`) con
  **ControlNet** — esta es la combinación técnica correcta para lo que pide
  Juan en el punto 4 (capa técnica vs. generativa): ControlNet permite
  condicionar la generación de imagen a un mapa de profundidad/bordes de la
  foto original, de forma que la IA "redecora" respetando la geometría real
  en vez de inventar una habitación distinta. Gratis en licencia, pero pide
  GPU (propia o alquilada).
- **`Nutlope/roomGPT`** (GitHub) — el proyecto original de RoomGPT, publicado
  en abierto; se puede autoalojar con tu propia clave de Replicate/Stability
  en vez de pagar el SaaS.
- **`SamurAIGPT/ai-room-declutter`** (GitHub) — alternativa más reciente,
  explícitamente descrita como "alternativa libre a RoomGPT/Reimagine Home",
  con Next.js + Stripe ya integrados si se quisiera cobrar por su uso.

**Lectura honesta**: igual que en visión, "gratis" = sin licencia, pero
generar una imagen realista con Stable Diffusion sin GPU tarda minutos en CPU
— de nuevo, un servidor con GPU (propio o alquilado por uso) es casi
obligatorio para que la experiencia sea utilizable.

## 3. LLM para el orquestador de lenguaje natural ("tengo 25.000€ para reformar...")

Esta es la única de las tres capacidades donde una opción **verdaderamente
gratuita y sin servidor con GPU dedicado** es razonable, porque los modelos
de lenguaje pequeños actuales corren en CPU/GPU de consumo con latencia
aceptable:

| Opción | Coste | Notas |
|---|---|---|
| **Claude Haiku 4.5** | \$1/\$5 por millón de tokens | El más barato de los tres grandes proveedores comerciales para esta tarea; sin necesidad de visión, solo de razonar sobre datos ya estructurados (presupuesto, familia, preferencias) — la tarea encaja bien con un modelo "mini". |
| **Gemini Flash-Lite** | Desde \$0,25/\$1,50 por millón, con capa gratuita | El más barato en bruto, con cuota gratis para probar el flujo completo sin coste antes de decidir. |
| **Ollama + modelo local** (Llama, Mistral, o similar, ejecutándose en un servidor propio o incluso en el equipo del usuario si tiene GPU) | Gratis (sin coste por token) | Es la opción "constrúyelo con esfuerzo" más realista de las tres categorías: un LLM de tamaño moderado para tareas de razonamiento estructurado (no visión) es viable en hardware modesto, y varias guías de 2026 documentan el flujo completo de despliegue. El coste que sí existe es el de alojar ese servidor (aunque sea barato) y mantenerlo. |

## 4. Resumen para decidir

| Capacidad | Más barato de pago | Más rápido de integrar | Gratis pero con esfuerzo real |
|---|---|---|---|
| Visión general (fotos/vídeo) | Gemini Flash-Lite (tiene capa gratis) | Gemini o Claude (API de propósito general, sin entrenamiento previo) | DeepFloorplan / YOLOv8 floor-plan (necesitan servidor con GPU) |
| Visión especializada en planos | Roboflow (con tu propio dataset etiquetado) | CubiCasa (pero sin precio de API público) | Entrenar un modelo propio sobre CubiCasa5k con Roboflow (capa gratuita) |
| Generación de interiores | Stability AI (\$0,03–\$0,08/imagen) | Replicate (miles de modelos ya listos) | Stable Diffusion + ControlNet autoalojado |
| Orquestador de lenguaje natural | Gemini Flash-Lite / Claude Haiku | Cualquiera de los tres grandes (API madura, buena documentación) | Ollama + modelo local |

## 5. Recomendación honesta y siguiente paso

Ninguna de estas piezas se puede "simplemente añadir" sin antes resolver el
problema de la sección 0 (dónde vive la clave). Dado que Juan no ha decidido
todavía introducir un backend, el camino de menor riesgo si se quiere
avanzar ahora mismo sin comprometer la promesa de "nada sale del
dispositivo" es:

1. Empezar por el **orquestador de lenguaje natural** (sección 3), no por
   visión ni generación de imagen: es la única capacidad donde correr un
   modelo pequeño localmente (Ollama) es realista hoy, y es la que menos
   depende de que exista ya un backend.
2. Dejar **visión real** y **generación de interiores** para cuando exista
   una decisión explícita sobre backend — no porque sean técnicamente más
   difíciles de integrar (la llamada HTTP es igual de sencilla en los tres
   casos), sino porque necesitan mover imágenes/vídeo, lo cual hace mucho
   menos práctico pedirle al usuario su propia API key (opción 2 de la
   sección 0) y hace más necesaria la opción 1 (backend propio).
3. Ninguna decisión de proveedor concreto se toma en este documento — sigue
   siendo una decisión de Juan, ahora con cifras reales delante en vez de sin
   ellas.

## Fuentes consultadas

- [Claude API pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [OpenAI API pricing](https://developers.openai.com/api/docs/pricing)
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Amazon Rekognition pricing](https://aws.amazon.com/rekognition/pricing/)
- [Azure AI Vision pricing](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/computer-vision/)
- [Stability AI API pricing breakdown](https://developer.puter.com/tutorials/stability-ai-api-pricing/)
- [Stability AI developer platform pricing](https://platform.stability.ai/pricing)
- [Replicate pricing comparison](https://pricepertoken.com/image)
- [CubiCasa pricing packages](https://www.cubi.casa/pricing/)
- [Roboflow pricing](https://roboflow.com/pricing)
- [DeepFloorplan (GitHub)](https://github.com/zlzeng/DeepFloorplan)
- [floor-plan-room-segmentation (GitHub)](https://github.com/ozturkoktay/floor-plan-room-segmentation)
- [floor-plan-object-detection, YOLOv8 (GitHub)](https://github.com/sanatladkat/floor-plan-object-detection)
- [roomGPT original, open-source (GitHub)](https://github.com/Nutlope/roomGPT)
- [ai-room-declutter, alternativa libre a RoomGPT (GitHub)](https://github.com/SamurAIGPT/ai-room-declutter)
- [Running LLMs locally with Ollama in 2026](https://daily.dev/blog/running-llms-locally-ollama-llama-cpp-self-hosted-ai-developers/)
