---
title: HomeAI Renovation
emoji: 🏠
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Servicio "Visualiza tu reforma con IA" (fase 1, MVP)

Microservicio mínimo que recibe una foto de una estancia y un estilo, y
devuelve la misma estancia redecorada con un modelo *image-to-image* de
Hugging Face. Lo usa la tarjeta **Visualiza tu reforma con IA** de la vista
Diseño (`ai-renovation.js`).

> El bloque YAML de arriba es la cabecera que exige un **Hugging Face Space**
> de tipo Docker. En GitHub se ve como una tabla; es normal.

## Por qué existe (decisión de arquitectura)

HomeAI es una web estática sin backend. El token de Hugging Face **no puede
vivir en el navegador**: cualquiera lo leería con las herramientas de
desarrollador. Por eso esto es un **microservicio aparte**, no un endpoint
"del backend actual", que no existe. Solo hace de proxy fino:

```
navegador                         este servicio                      Hugging Face
─────────                         ─────────────                      ────────────
foto ─► reduce a ≤1024 px,  ─►  valida formato/tamaño,       ─►  Inference Providers
        quita EXIF/GPS,          re-codifica (quita metadatos),     image_to_image(model,
        consentimiento           aplica orientación, ≤1024 px,      prompt, strength…)
                                 múltiplo de 8, autocontraste   ◄─  imagen resultado
◄─ JPEG resultado  ◄───────────  si la foto es muy oscura
   (antes/después,               límite por IP y concurrencia,
    guardar o descartar)         errores traducidos a códigos claros
```

- **Fase 1 (esto):** Inference Providers vía `huggingface_hub.InferenceClient`,
  sin GPU propia. El servicio no necesita GPU (solo reenvía), así que cabe en
  el plan gratuito de CPU de un Space.
- **Fase 2 (si el uso crece o la calidad no basta):** apuntar `HF_MODEL` a la
  URL de un **Inference Endpoint** dedicado (acepta una URL en vez de un id de
  modelo), con un handler propio de Stable Diffusion + ControlNet (depth o
  canny). Es lo que de verdad "bloquea" la geometría; img2img solo la conserva
  en la medida en que `strength` sea bajo. El navegador no cambia.

## Zonas: transformar solo pared, suelo, techo o mobiliario

```
foto ─► POST /api/segment ─► SegFormer-b4 (ADE20K, CPU, dentro del servicio)
                             └► mapa de zonas (PNG) + % por zona ─► navegador
navegador: el usuario toca zonas / ajusta con pincel ─► máscara PNG
foto + máscara + estilo ─► POST /api/renovate ─► modelo (imagen entera)
                             └► composición: resultado SOLO dentro de la máscara
```

- **Por qué b4:** validado con 10 fotos reales de pisos frente a b0 y b2
  (`validation/results_compare/compare.md`): mejor en todas las zonas,
  sobre todo mobiliario (confianza 0,69 → 0,86), a ~3 s por foto en 2 núcleos.
- **Cuándo se calcula:** una vez por foto, al subirla. El servidor **no la
  guarda**: devuelve el mapa y el navegador lo conserva en memoria mientras el
  usuario elige; al generar envía la selección como máscara. El servicio sigue
  sin estado (escala y no retiene fotos).
- **Por qué composición y no inpainting:** `InferenceClient` no tiene una
  tarea de inpainting con máscara y no hay garantía de que el proveedor la
  tenga. Se genera la imagen entera y se pega solo dentro de la máscara, con
  el borde suavizado hacia dentro: **fuera de la zona elegida la foto queda
  idéntica** (en la respuesta, salvo la compresión JPEG). Comprobado con el
  modelo real sobre 6 fotos en `validation/results_server/report.md`.
  En la fase 2, un endpoint de inpainting real puede recibir la misma máscara.
- **Límites conocidos** (de la validación): pared/suelo/techo fiables;
  mobiliario peor en armarios blancos sobre pared blanca; espejos y cristales
  confunden al modelo (el espejo se excluye de las zonas). Por eso la
  interfaz muestra la selección en verde y permite corregirla con un pincel.
- La primera versión de la imagen Docker pesa bastante más (PyTorch +
  modelo, ~2 GB); sigue cabiendo en un Space CPU gratuito. El modelo se
  descarga al construir la imagen, no en la primera petición.

## Estilo actual de la habitación: `POST /api/style`

- CLIP `openai/clip-vit-large-patch14` en modo zero-shot, dentro del servicio
  (sin crédito de HF, sin enviar la foto a otro tercero). ~1,3 s por foto en 2
  núcleos. Se llama al subir la foto, en paralelo a la detección de zonas.
- **Solo se afirma un estilo si el modelo está seguro:** probabilidad del
  primero ≥ 0,5 y ventaja ≥ 0,2 sobre el segundo (`STYLE_MIN_PROB`,
  `STYLE_MIN_MARGIN`). Tres etiquetas de "no sugerir" — habitación vacía,
  primer plano de un objeto, exterior — ganan cuando la foto no muestra una
  estancia con muebles. Respuesta: `{style, label, confidence, margin,
  suggest, reason, top}`; con `suggest=false`, `style` es `null` y `reason`
  explica por qué.
- Validación (`validation/results_style/`): con fotos revisadas a mano,
  large/14 acierta 6/7 (base/32, el modelo propuesto inicialmente, 3–4/8);
  con el umbral, lo que se sugiere acierta 6/6, y en 10/10 fotos que no son un
  estilo (vacías, exteriores, detalles) no se sugiere nada. **Sin validar con
  fotos buenas: escandinavo, bohemio y mediterráneo** (Wikimedia y Openverse no
  tenían ejemplos fiables).
- La interfaz lo muestra como "Parece: Rústico ▾" sobre la foto (editable) y
  marca 2–3 estilos de destino como sugeridos; nunca selecciona nada solo.
- La imagen Docker crece: CLIP large ocupa ~1,7 GB (total ~4 GB). Si pesa
  demasiado, `STYLE_MODEL=openai/clip-vit-base-patch32` reduce ~1,1 GB a
  costa de precisión (ver validación).

## Varias versiones por petición: filtro de similitud y de calidad

Lógica en `pipeline.py` (la misma que ejecuta el notebook de Colab).

- `POST /api/renovate` acepta `variants` (1–2; la interfaz pide 2; `VARIANTS_MAX`
  no puede subirlo de 2 porque el coste es por imagen). Se generan **en
  paralelo** y se aplica la máscara de zonas a cada una.
- **Paso 1, filtro de similitud (antes del puntuador):** similitud coseno CLIP
  entre cada versión y el original (con zonas, en el recorte de la zona). Si
  supera `SIMILARITY_MAX` (0,89) la versión es «casi idéntica»: se descarta
  (`reason: "sin_cambios"`) y **se regenera una vez** (una llamada más por cada
  una, que cuenta para el límite por hora). Un hash perceptual no sirve aquí:
  una versión solo más luminosa ya lo cambia mucho y CLIP sí la reconoce como
  la misma foto.
- **Paso 2, puntuador:** solo las que pasan el filtro se puntúan con
  `quality.py` (predictor estético de LAION + realismo por CLIP, el mismo CLIP
  large/14 de la detección de estilo). Nota < `QUALITY_MIN_SCORE` (0,5) →
  `calidad_baja`. Las de calidad baja **no** se regeneran (coste).
- Se muestra la mejor no descartada; si no queda ninguna, antes una de calidad
  baja que una sin cambios, con `low_quality: true`. Peor caso: 4 llamadas
  al modelo por petición (2 + 2 regeneraciones).
- Con `variants > 1` la respuesta es JSON: `{best, retried, regenerated,
  low_quality, variants: [{image (data URL JPEG), score, aesthetic, realism,
  similarity, discarded, reason}]}`; con `variants = 1`, JPEG como antes.
- Si CLIP o el puntuador fallan, se devuelven las versiones sin ese filtro.
- `SIMILARITY_MAX` sale de una sola foto real (FLUX Kontext): **provisional**
  hasta la medición en Colab (`validation/colab/`), que mide la similitud de
  cada generación con Qwen-Image-Edit.

## Modelo: Qwen-Image-Edit

- Por defecto `Qwen/Qwen-Image-Edit` (Apache-2.0, uso comercial). SDXL ya no lo
  sirve ningún proveedor para image-to-image; FLUX.1 Kontext [dev] se descartó
  por su licencia no comercial. Comprobar antes de desplegar:
  `HF_TOKEN=hf_xxx python check_model.py Qwen/Qwen-Image-Edit` (en septiembre de
  2026 lo servían fal-ai y wavespeed).
- **Es un modelo de edición por instrucciones, no img2img:** el texto lo lee
  Qwen2.5-VL mirando la foto (semántica) y el VAE conserva la apariencia. Por
  eso `pipeline.build_prompt` escribe una instrucción en inglés («Redecorate
  this room in this style: …. Keep the same room and the same camera
  angle…»), con el estilo del usuario tal cual (Qwen2.5-VL entiende español).
- **No existe `strength`:** la intensidad de la interfaz (0,30–0,80) se traduce
  a la instrucción (≤0,45 retoque de colores/textiles/decoración; ≤0,65 cambiar
  muebles y acabados; más, rediseño completo). `strength` solo se sigue
  enviando si `HF_MODEL` es un img2img clásico.
- La guía de Qwen es `true_cfg_scale` con prompt negativo (4 por defecto, 30
  pasos en fal-ai). El resultado sale a ~1 MP y se devuelve al tamaño de la
  foto.
- Coste por la API: fal-ai cobra ~0,03 $ por megapíxel → ~0,03 $ por imagen,
  ~0,06 $ por petición de 2 versiones (hasta ~0,12 $ con regeneraciones).
  Pendiente de confirmar con `validation/api_cost_probe.py`.

### Backend propio con GPU (`GEN_BACKEND=diffusers`)

`local_qwen.py` ejecuta el mismo modelo con diffusers (`QwenImageEditPipeline`)
en una GPU propia, con la misma interfaz que la API (el filtro de similitud y
el puntuador no cambian). Instalar `requirements-gpu.txt` sobre un torch CUDA.
El modelo son ~54 GB en bf16 (transformer 20B + Qwen2.5-VL 7B): con
`QWEN_QUANT=nf4` (4 bits) cabe en una GPU de 24 GB; sin cuantizar hace falta
una de 80 GB. `QWEN_LIGHTNING=1` usa la LoRA Lightning (8 pasos sin CFG).
**No probado con los pesos reales** (este entorno no tiene GPU); el código se
comprueba en CI con un modelo diminuto (`validation/colab/smoke_test.py`).

## Parámetros

| Variable | Por defecto | Qué hace |
|---|---|---|
| `HF_TOKEN` | — (**obligatoria**) | Token *fine-grained* con permiso "Make calls to Inference Providers". Como **secreto**, nunca en el repo. |
| `HF_MODEL` | `Qwen/Qwen-Image-Edit` | Id del modelo o URL de un Inference Endpoint. SDXL (el valor anterior) no lo sirve ningún proveedor para image-to-image. |
| `HF_PROVIDER` | `auto` | Proveedor (`auto`, `fal-ai`, `replicate`, `hf-inference`…). |
| `GEN_BACKEND` | `api` | `api` (Inference Providers de HF) o `diffusers` (GPU propia, `local_qwen.py`). |
| `HF_STEPS` / `HF_GUIDANCE_SCALE` | `30` / `4.0` | Pasos y guía (`true_cfg_scale` en Qwen). |
| `QWEN_QUANT` / `QWEN_LIGHTNING` / `QWEN_DTYPE` | `nf4` / `0` / `auto` | Solo con `GEN_BACKEND=diffusers`. |
| `HF_TIMEOUT_SECONDS` | `120` | Espera máxima al proveedor. |
| `ALLOWED_ORIGINS` | `https://homeai.juancopado.chatgpt.site` | Orígenes CORS permitidos, separados por comas. |
| `RATE_LIMIT_PER_HOUR` | `10` | Generaciones por IP y hora (en memoria, una sola réplica). |
| `MAX_CONCURRENT_GENERATIONS` | `2` | Generaciones simultáneas; el resto recibe `busy`. |
| `MAX_UPLOAD_MB` / `MAX_IMAGE_SIDE` | `10` / `1024` | Límites de subida y de resolución enviada al modelo. |
| `SEG_MODEL` | `nvidia/segformer-b4-finetuned-ade-512-512` | Modelo de segmentación (se ejecuta en el propio servicio). |
| `SEG_RATE_LIMIT_PER_HOUR` / `MAX_CONCURRENT_SEGMENTATIONS` | `30` / `2` | Límite propio de la detección de zonas (usa CPU del servicio, no crédito de HF). La concurrencia se comparte con la detección de estilo. |
| `STYLE_MODEL` | `openai/clip-vit-large-patch14` | Modelo de detección de estilo. |
| `STYLE_MIN_PROB` / `STYLE_MIN_MARGIN` | `0.5` / `0.2` | Umbral para afirmar un estilo (validado). |
| `STYLE_RATE_LIMIT_PER_HOUR` | `30` | Límite propio de la detección de estilo. |
| `VARIANTS_MAX` | `2` | Máximo de versiones por petición (tope fijo 2). |
| `SIMILARITY_MAX` | `0.89` | Por encima, «casi idéntica» al original: se descarta y se regenera una vez. |
| `QUALITY_MIN_SCORE` | `0.5` | Nota mínima del puntuador (ver calibración). |
| `AESTHETIC_WEIGHTS_URL` | GitHub de improved-aesthetic-predictor | Pesos del predictor estético (se descargan al construir la imagen). |

## Desplegar en un Hugging Face Space (recomendado para la fase 1)

1. En huggingface.co → *New Space* → SDK **Docker**, hardware **CPU basic**
   (gratis).
2. Sube el contenido de esta carpeta `server/` a la raíz del Space (este
   `README.md` incluido: su cabecera configura el Space).
3. En *Settings → Variables and secrets*: añade `HF_TOKEN` como **Secret** y,
   si hace falta, `HF_MODEL` / `HF_PROVIDER` como variables.
4. Comprueba `https://<usuario>-<space>.hf.space/api/health` → debe responder
   `"configured": true`.
5. En `index.html` de HomeAI, pon esa URL en
   `<meta name="homeai-renovation-endpoint" content="…">`, ejecuta
   `node build.mjs` y publica.

Alternativas equivalentes: cualquier servicio que ejecute el `Dockerfile`
(Railway, Fly.io, Cloud Run…). Solo cambia dónde se guarda el secreto.

Local:

```
pip install -r requirements-dev.txt
pytest -q                                   # 88 tests, sin llamar a Hugging Face
HF_TOKEN=hf_xxx ALLOWED_ORIGINS=http://localhost:8000 uvicorn app:app --port 7860
```

Y en la consola del navegador, sobre HomeAI servido en local:
`localStorage.setItem('homeai.renovationEndpoint','http://localhost:7860')`.

## Plan gratuito de Hugging Face y qué pasa al agotarse

Según la documentación de precios de Hugging Face al escribir esto (**verificar
en huggingface.co/pricing antes de lanzar**, cambia a menudo):

- Las cuentas gratuitas reciben un crédito mensual pequeño para Inference
  Providers (del orden de céntimos de dólar al mes); las PRO, algo más y
  pueden pagar el exceso por uso. Una imagen img2img cuesta del orden de
  céntimos según proveedor y modelo, así que **el crédito gratuito da para
  muy pocas visualizaciones**. Sirve para validar, no para usuarios reales.
- Al agotarse, Hugging Face responde **HTTP 402**. El servicio lo traduce a
  `quota_exhausted` (503) y la tarjeta muestra "La IA de HomeAI ha agotado su
  crédito por ahora". Nada más se rompe: el resto de HomeAI sigue igual.
- Los límites de ritmo del proveedor (HTTP 429) se muestran como
  `provider_rate_limited` con reintento sugerido.
- Para no gastar crédito en abusos: límite por IP (`RATE_LIMIT_PER_HOUR`) y de
  concurrencia (`MAX_CONCURRENT_GENERATIONS`). Para uso público real conviene
  además una cuenta con facturación y un tope de gasto en Hugging Face.

## Privacidad (lo que hace y lo que no)

- **Qué sale del dispositivo:** solo cuando el usuario marca el consentimiento
  y pulsa "Generar". Sale una copia **reducida (≤1024 px) y re-codificada**:
  sin EXIF, así que sin GPS, modelo de móvil ni fecha. Más el texto del estilo.
- **Este servicio:** no escribe nada en disco (ni siquiera archivos temporales: el tamaño se comprueba antes de leer la subida y esta se mantiene en memoria), no registra fotos ni textos (los
  logs solo guardan tamaño, `strength` y duración) y responde con
  `Cache-Control: no-store`. La foto vive en memoria durante la petición.
- **Hugging Face y el proveedor:** la foto pasa por el router de Hugging Face
  y por el proveedor que sirva el modelo (p. ej. fal-ai o Replicate), cada uno
  con su propia política de retención. **Revisar esas políticas antes de abrir
  la función al público** y reflejarlas en el aviso de privacidad de HomeAI.
- **Zonas:** la foto se segmenta dentro de este servicio (no se envía a
  ningún tercero para eso). Ni el mapa de zonas ni la máscara se guardan: el
  mapa vuelve al navegador y la máscara solo vive durante la petición.
- **El resultado:** solo se guarda si el usuario pulsa "Guardar en Archivos",
  y entonces solo en su navegador (IndexedDB), como el resto de documentos.

## Límites conocidos de la fase 1

- Ningún modelo generativo garantiza la geometría: con intensidad alta puede
  mover ventanas o inventar muebles. El texto de la tarjeta lo advierte. ControlNet, en la
  fase 2.
- El límite por IP vive en memoria: se reinicia al reiniciar el Space y no se
  comparte entre réplicas.
- Detrás de un proxy que no sea el de Hugging Face, revisar
  `--forwarded-allow-ips` en el `Dockerfile`: tal como está, confía en
  `X-Forwarded-For` y un cliente directo podría falsear su IP.
- HEIC (iPhone) no se admite; la tarjeta explica cómo convertirlo.
