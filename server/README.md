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

## Modelo: lo que hay que saber antes de desplegar

- `image_to_image` solo funciona con modelos que **algún proveedor sirva para
  esa tarea**. Qué modelos están servidos cambia con el tiempo y **no se pudo
  comprobar al escribir esto** (el entorno de desarrollo no tenía acceso a
  huggingface.co). Antes de desplegar, ejecuta:

  ```
  HF_TOKEN=hf_xxx python check_model.py stabilityai/stable-diffusion-xl-base-1.0
  ```

  Si responde "ningún proveedor lo sirve", prueba otro candidato y pon el que
  funcione en `HF_MODEL`. Candidatos, por orden de preferencia para este caso:
  1. Modelos de **edición por instrucciones** (p. ej. de la familia FLUX Kontext
     o Qwen-Image-Edit, si aparecen servidos para image-to-image): suelen
     respetar la estructura de la foto mucho mejor que img2img clásico.
  2. `stabilityai/stable-diffusion-xl-base-1.0` (img2img con `strength`).
  3. SD 1.5 + ControlNet depth: **no** está disponible como image-to-image
     serverless. Necesita la fase 2 (Endpoint o Space con GPU). Nota: el repo
     `runwayml/stable-diffusion-v1-5` fue retirado; el espejo actual es
     `stable-diffusion-v1-5/stable-diffusion-v1-5`.
- `strength` (0,30–0,80; la tarjeta usa 0,55 por defecto) se envía como
  parámetro extra. Los modelos de edición por instrucciones lo ignoran.

## Parámetros

| Variable | Por defecto | Qué hace |
|---|---|---|
| `HF_TOKEN` | — (**obligatoria**) | Token *fine-grained* con permiso "Make calls to Inference Providers". Como **secreto**, nunca en el repo. |
| `HF_MODEL` | `stabilityai/stable-diffusion-xl-base-1.0` | Id del modelo o URL de un Inference Endpoint. |
| `HF_PROVIDER` | `auto` | Proveedor (`auto`, `fal-ai`, `replicate`, `hf-inference`…). |
| `HF_STEPS` / `HF_GUIDANCE_SCALE` | `30` / `7.0` | Pasos de difusión y adherencia al texto. |
| `HF_TIMEOUT_SECONDS` | `120` | Espera máxima al proveedor. |
| `ALLOWED_ORIGINS` | `https://homeai.juancopado.chatgpt.site` | Orígenes CORS permitidos, separados por comas. |
| `RATE_LIMIT_PER_HOUR` | `10` | Generaciones por IP y hora (en memoria, una sola réplica). |
| `MAX_CONCURRENT_GENERATIONS` | `2` | Generaciones simultáneas; el resto recibe `busy`. |
| `MAX_UPLOAD_MB` / `MAX_IMAGE_SIDE` | `10` / `1024` | Límites de subida y de resolución enviada al modelo. |

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
pytest -q                                   # 32 tests, sin llamar a Hugging Face
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
- **El resultado:** solo se guarda si el usuario pulsa "Guardar en Archivos",
  y entonces solo en su navegador (IndexedDB), como el resto de documentos.

## Límites conocidos de la fase 1

- img2img no garantiza la geometría: con `strength` alto puede mover ventanas
  o inventar muebles. El texto de la tarjeta lo advierte. ControlNet, en la
  fase 2.
- El límite por IP vive en memoria: se reinicia al reiniciar el Space y no se
  comparte entre réplicas.
- Detrás de un proxy que no sea el de Hugging Face, revisar
  `--forwarded-allow-ips` en el `Dockerfile`: tal como está, confía en
  `X-Forwarded-For` y un cliente directo podría falsear su IP.
- HEIC (iPhone) no se admite; la tarjeta explica cómo convertirlo.
