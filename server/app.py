"""Servicio de "Visualización de reforma con IA" para HomeAI (fase 1, MVP).

HomeAI es una web estática sin backend. Este microservicio existe solo para
que el token de Hugging Face viva en el servidor (variable de entorno
HF_TOKEN) y nunca en el navegador. Hace de proxy fino:

    foto + estilo -> validar y re-codificar -> Inference API (image-to-image)
                  -> imagen resultado (JPEG) de vuelta al navegador

Privacidad (ver README.md): no guarda nada en disco, no registra ni fotos ni
textos, y re-codifica la foto antes de enviarla (elimina EXIF/GPS y reduce la
resolución a lo que el modelo necesita).
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re
import threading
import time
from collections import defaultdict, deque

import numpy as np
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError
from starlette.formparsers import MultiPartParser

import segmentation as seg
import style as style_mod

log = logging.getLogger("homeai.renovation")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Protección contra "bombas de descompresión" (una imagen pequeña en bytes que
# ocupa gigas al decodificarla). 40 MP cubre de sobra cualquier foto de móvil.
Image.MAX_IMAGE_PIXELS = 40_000_000

# Starlette vuelca a un archivo temporal en disco las partes de más de 1 MB.
# Se sube el umbral por encima del límite de subida (que se comprueba antes
# de leer el cuerpo, ver limit_body_size) para que la foto nunca toque disco.
MultiPartParser.spool_max_size = 64 * 1024 * 1024

ACCEPTED_FORMATS = {"JPEG", "PNG", "WEBP"}
MIN_SIDE = 256
MAX_ASPECT = 3.0
MAX_STYLE_CHARS = 300

STRUCTURE_SUFFIX = (
    "same room, same camera angle, keep walls, windows, doors, ceiling and floor layout "
    "exactly in place, realistic interior design photograph, natural light, high detail"
)
DEFAULT_NEGATIVE = (
    "different room, changed layout, moved windows, extra doors, distorted walls, "
    "warped perspective, people, text, watermark, blurry, low quality, cartoon"
)


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def settings() -> dict:
    """Se lee en cada petición para que la configuración se pueda cambiar
    (y probar) sin reiniciar el proceso."""
    return {
        "token": os.environ.get("HF_TOKEN", "").strip(),
        # SDXL no lo sirve ningún proveedor para image-to-image (comprobado con
        # token real, validation/results_variants/). Qwen-Image-Edit: servido
        # (fal-ai, wavespeed) y Apache-2.0. Alternativa medida:
        # black-forest-labs/FLUX.1-Kontext-dev (licencia no comercial de pesos).
        "model": os.environ.get("HF_MODEL", "Qwen/Qwen-Image-Edit"),
        "provider": os.environ.get("HF_PROVIDER", "auto"),
        "timeout": env_float("HF_TIMEOUT_SECONDS", 120),
        "max_upload": env_int("MAX_UPLOAD_MB", 10) * 1024 * 1024,
        "max_side": env_int("MAX_IMAGE_SIDE", 1024),
        "steps": env_int("HF_STEPS", 30),
        "guidance": env_float("HF_GUIDANCE_SCALE", 7.0),
        "rate_per_hour": env_int("RATE_LIMIT_PER_HOUR", 10),
        "max_concurrent": env_int("MAX_CONCURRENT_GENERATIONS", 2),
        "seg_rate_per_hour": env_int("SEG_RATE_LIMIT_PER_HOUR", 30),
        "seg_concurrent": env_int("MAX_CONCURRENT_SEGMENTATIONS", 2),
        "style_rate_per_hour": env_int("STYLE_RATE_LIMIT_PER_HOUR", 30),
        # Variantes por petición y filtro de calidad (server/quality.py).
        # Umbrales calibrados en validation/results_quality/report.md
        # (min_change es provisional: sale de una sola foto real).
        "variants_max": env_int("VARIANTS_MAX", 3),
        "min_score": env_float("QUALITY_MIN_SCORE", 0.5),
        "min_change": env_float("QUALITY_MIN_CHANGE", 0.11),
    }


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.retry_after = status, code, message, retry_after


# --- Límite de uso -----------------------------------------------------------
# En memoria: suficiente para una sola instancia (un Space). Si se escala a
# varias réplicas, hay que moverlo a un almacén compartido.

_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()
_slots_lock = threading.Lock()
_active = 0
_seg_active = 0


def check_rate_limit(client_id: str, per_hour: int, weight: int = 1) -> None:
    """weight = cuántas unidades consume la petición (cada variante generada
    gasta crédito, así que cuenta como una visualización)."""
    if per_hour <= 0:
        return
    now = time.monotonic()
    with _hits_lock:
        q = _hits[client_id]
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) + weight > per_hour:
            retry = int(3600 - (now - q[0])) + 1 if q else 3600
            raise ApiError(429, "rate_limited", "Has alcanzado el límite de visualizaciones por hora. Prueba más tarde.", retry)
        q.extend([now] * weight)


def acquire_slot(max_concurrent: int) -> None:
    global _active
    with _slots_lock:
        if _active >= max_concurrent:
            raise ApiError(503, "busy", "El servicio está ocupado con otras visualizaciones. Inténtalo en un minuto.", 30)
        _active += 1


def release_slot() -> None:
    global _active
    with _slots_lock:
        _active = max(0, _active - 1)


def acquire_seg_slot(max_concurrent: int) -> None:
    global _seg_active
    with _slots_lock:
        if _seg_active >= max_concurrent:
            raise ApiError(503, "busy", "El servicio está ocupado analizando otras fotos. Inténtalo en unos segundos.", 10)
        _seg_active += 1


def release_seg_slot() -> None:
    global _seg_active
    with _slots_lock:
        _seg_active = max(0, _seg_active - 1)


# --- Preprocesado --------------------------------------------------------------

def preprocess(data: bytes, max_side: int) -> Image.Image:
    """Valida la foto y devuelve una imagen RGB nueva, sin metadatos, con la
    orientación EXIF aplicada y dimensiones múltiplo de 8 (lo que esperan los
    modelos de difusión)."""
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            probe.verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except Image.DecompressionBombError as exc:
        raise ApiError(413, "image_too_large", "La imagen tiene demasiados píxeles.") from exc
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ApiError(415, "unsupported_format", "No se pudo leer la imagen. Usa una foto JPG, PNG o WebP.") from exc
    if fmt not in ACCEPTED_FORMATS:
        raise ApiError(415, "unsupported_format", "Formato no admitido. Usa una foto JPG, PNG o WebP.")

    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        base = Image.new("RGB", rgba.size, (255, 255, 255))
        base.paste(rgba, mask=rgba.getchannel("A"))
        img = base
    else:
        img = img.convert("RGB")

    w, h = img.size
    if min(w, h) < MIN_SIDE:
        raise ApiError(400, "image_too_small", f"La foto es demasiado pequeña (mínimo {MIN_SIDE} px por lado).")
    if max(w, h) / min(w, h) > MAX_ASPECT:
        raise ApiError(400, "bad_aspect_ratio", "La foto es demasiado alargada (p. ej. una panorámica). Usa una foto normal de la estancia.")

    scale = min(1.0, max_side / max(w, h))
    nw, nh = max(8, int(w * scale) // 8 * 8), max(8, int(h * scale) // 8 * 8)
    if (nw, nh) != (w, h):
        img = img.resize((nw, nh), Image.LANCZOS)

    # Fotos muy oscuras: el modelo tiende a inventar la escena. Un autocontraste
    # suave recupera las formas (paredes, ventanas) sin alterar la composición.
    if ImageStat.Stat(img.convert("L")).mean[0] < 50:
        img = ImageOps.autocontrast(img, cutoff=1)
    return img


def clean_style(style: str) -> str:
    style = re.sub(r"[\x00-\x1f\x7f]+", " ", style or "").strip()
    style = re.sub(r"\s+", " ", style)
    if len(style) < 3:
        raise ApiError(400, "style_required", "Describe el estilo que quieres (por ejemplo: «nórdico, tonos claros, madera»).")
    if len(style) > MAX_STYLE_CHARS:
        raise ApiError(400, "style_too_long", f"La descripción del estilo es demasiado larga (máximo {MAX_STYLE_CHARS} caracteres).")
    return style


# --- Llamada al modelo ---------------------------------------------------------

def make_client(cfg: dict):
    from huggingface_hub import InferenceClient

    return InferenceClient(provider=cfg["provider"], token=cfg["token"], timeout=cfg["timeout"])


def map_hf_error(exc: Exception) -> ApiError:
    from huggingface_hub.errors import HfHubHTTPError, InferenceTimeoutError

    if isinstance(exc, InferenceTimeoutError):
        return ApiError(504, "timeout", "El modelo tardó demasiado en responder. Inténtalo de nuevo en un momento.", 20)
    if isinstance(exc, HfHubHTTPError):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 402:
            return ApiError(503, "quota_exhausted", "Se ha agotado el crédito de IA del servicio. La función vuelve a estar disponible cuando se renueve.")
        if status == 429:
            return ApiError(429, "provider_rate_limited", "El proveedor de IA está limitando las peticiones. Espera un minuto y reinténtalo.", 60)
        if status in (401, 403):
            log.error("Hugging Face rechazó el token (HTTP %s): revisar HF_TOKEN y sus permisos", status)
            return ApiError(503, "not_configured", "El servicio de IA no está bien configurado ahora mismo.")
        if status == 503:
            return ApiError(503, "model_loading", "El modelo se está iniciando. Vuelve a intentarlo en unos segundos.", 20)
        if status in (400, 404, 422):
            log.error("El proveedor rechazó la petición (HTTP %s)", status)
            return ApiError(502, "model_unsupported", "El modelo configurado no acepta esta petición. Hay que revisar HF_MODEL/HF_PROVIDER.")
        return ApiError(502, "upstream_error", "El servicio de IA ha fallado. Inténtalo de nuevo.")
    if isinstance(exc, ValueError):
        # get_provider_helper lanza ValueError si ningún proveedor sirve ese
        # modelo para image-to-image.
        log.error("Modelo sin proveedor para image-to-image: %s", exc)
        return ApiError(502, "model_unsupported", "El modelo configurado no está disponible para transformar fotos. Hay que revisar HF_MODEL/HF_PROVIDER.")
    log.exception("Error inesperado llamando al modelo")
    return ApiError(502, "upstream_error", "El servicio de IA ha fallado. Inténtalo de nuevo.")


def build_prompt(style: str, zones: list[str]) -> str:
    if not zones:
        return f"{style}, {STRUCTURE_SUFFIX}"
    target = " and ".join(seg.ZONE_PROMPT[z] for z in zones)
    return f"{target} redesigned: {style}, {STRUCTURE_SUFFIX}"


def parse_zones(raw: str) -> list[str]:
    zones = [z.strip() for z in (raw or "").split(",") if z.strip()]
    if any(z not in seg.ZONE_PROMPT for z in zones):
        raise ApiError(400, "invalid_zones", "Zona no válida.")
    return list(dict.fromkeys(zones))


def read_mask(upload_bytes: bytes, size: tuple[int, int]):
    try:
        with Image.open(io.BytesIO(upload_bytes)) as probe:
            fmt = probe.format
            probe.verify()
        mask_img = Image.open(io.BytesIO(upload_bytes))
        mask_img.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ApiError(400, "invalid_mask", "La selección de zonas no es válida. Vuelve a seleccionarlas.") from exc
    if fmt != "PNG":
        raise ApiError(400, "invalid_mask", "La selección de zonas no es válida. Vuelve a seleccionarlas.")
    mask = seg.parse_mask(mask_img, size)
    if not mask.any():
        raise ApiError(400, "empty_mask", "No hay ninguna zona seleccionada. Toca una zona de la foto o elige «Toda la foto».")
    return mask


def generate(img: Image.Image, prompt: str, strength: float, cfg: dict) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    client = make_client(cfg)
    try:
        result = client.image_to_image(
            buf.getvalue(),
            prompt=prompt,
            negative_prompt=DEFAULT_NEGATIVE,
            num_inference_steps=cfg["steps"],
            guidance_scale=cfg["guidance"],
            model=cfg["model"],
            # Cuánto se aleja de la foto original (0 = igual, 1 = imagen nueva).
            # No es un argumento con nombre de image_to_image: se envía como
            # parámetro extra y lo usan los modelos img2img que lo admiten.
            strength=strength,
        )
    except Exception as exc:  # noqa: BLE001 - se traduce a un error de API claro
        raise map_hf_error(exc) from exc
    return result.convert("RGB")


def generate_variants(img, prompt, strength, cfg, n, mask_arr):
    """Genera n variantes EN PARALELO (la latencia es la de la más lenta, no la
    suma: 1 variante 45 s frente a 2 en paralelo 28 s en la medición real),
    aplica la máscara a cada una y las puntúa frente al original.

    Devuelve (variantes, primer_error). Una variante que falla no tumba a las
    demás; si fallan todas, el llamante lanza el primer error.
    """
    from concurrent.futures import ThreadPoolExecutor

    def one(_):
        try:
            out = generate(img, prompt, strength, cfg)
        except ApiError as exc:
            return exc
        if mask_arr is not None:
            out = seg.composite(img, out, mask_arr)
        return out

    with ThreadPoolExecutor(n) as ex:
        results = list(ex.map(one, range(n)))
    variants = [{"image": r} for r in results if not isinstance(r, ApiError)]
    first_error = next((r for r in results if isinstance(r, ApiError)), None)
    box = None
    if mask_arr is not None:
        ys, xs = np.nonzero(mask_arr)
        pad = 8
        box = (max(0, xs.min() - pad), max(0, ys.min() - pad), min(img.width, xs.max() + pad + 1), min(img.height, ys.max() + pad + 1))
    try:
        import quality

        for v in variants:
            v.update(quality.score(v["image"], img, box))
    except Exception:  # noqa: BLE001 - sin puntuador se devuelven sin filtrar
        log.exception("Fallo del puntuador de calidad; se devuelven las variantes sin filtrar")
    return variants, first_error


def judge(variants: list[dict], cfg: dict) -> None:
    """Marca descartes: sin cambios respecto al original (el modelo "no hizo
    nada") o calidad por debajo del umbral. Con zonas, "change" ya viene
    medido sobre el recorte de la zona (generate_variants), así que el mismo
    umbral vale en los dos modos."""
    min_change = cfg["min_change"]
    for v in variants:
        if "score" not in v:
            v["discarded"], v["reason"] = False, None
        elif v.get("change") is not None and v["change"] < min_change:
            v["discarded"], v["reason"] = True, "sin_cambios"
        elif v["score"] < cfg["min_score"]:
            v["discarded"], v["reason"] = True, "calidad_baja"
        else:
            v["discarded"], v["reason"] = False, None


def pick_best(variants: list[dict]) -> int:
    """La de más nota entre las no descartadas. Si todas lo están, antes una de
    «calidad baja» que una «sin cambios»: mostrar la foto tal cual no sirve."""
    rank = {None: 0, "calidad_baja": 1, "sin_cambios": 2}

    def key(i):
        v = variants[i]
        if v.get("reason") == "sin_cambios":  # entre las "sin cambios", la que más cambió
            return (2, -(v.get("change") or 0))
        return (rank.get(v.get("reason"), 1), -v.get("score", 0))

    return min(range(len(variants)), key=key)


def to_jpeg(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


# --- API -------------------------------------------------------------------------

app = FastAPI(title="HomeAI renovation", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "https://homeai.juancopado.chatgpt.site").split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    expose_headers=["Retry-After"],
    max_age=600,
)


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    """Rechaza cuerpos grandes ANTES de que se lean y se parseen: sin esto, una
    subida de varios GB se procesaría entera antes de llegar a renovate()."""
    if request.method == "POST" and request.url.path in ("/api/renovate", "/api/segment", "/api/style"):
        # margen para el resto del formulario, incluida la máscara PNG (≤1024 px, 1 bit útil)
        limit = settings()["max_upload"] + 2 * 1024 * 1024
        length = request.headers.get("content-length")
        if length is None:
            return await api_error_handler(request, ApiError(411, "length_required", "Falta la cabecera Content-Length."))
        if not length.isdigit() or int(length) > limit:
            return await api_error_handler(request, ApiError(413, "image_too_large", f"La foto pesa demasiado (máximo {settings()['max_upload'] // (1024 * 1024)} MB)."))
    return await call_next(request)


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError):
    headers = {"Cache-Control": "no-store"}
    if exc.retry_after:
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse({"error": exc.code, "message": exc.message}, status_code=exc.status, headers=headers)


@app.get("/api/health")
def health():
    cfg = settings()
    return {"ok": True, "configured": bool(cfg["token"]), "model": cfg["model"], "provider": cfg["provider"]}


async def read_photo(image: UploadFile, cfg: dict) -> Image.Image:
    data = await image.read(cfg["max_upload"] + 1)
    if len(data) > cfg["max_upload"]:
        raise ApiError(413, "image_too_large", f"La foto pesa demasiado (máximo {cfg['max_upload'] // (1024 * 1024)} MB).")
    return preprocess(data, cfg["max_side"])


@app.post("/api/segment")
async def segment_photo(request: Request, image: UploadFile = File(...)):
    """Detecta zonas (pared, suelo, techo, mobiliario…) en la foto.

    No guarda nada: devuelve el mapa al navegador, que lo conserva mientras el
    usuario elige zonas y lo reenvía como máscara al generar. Así la
    segmentación se calcula una sola vez por foto y el servidor sigue sin estado.
    """
    from starlette.concurrency import run_in_threadpool

    cfg = settings()
    img = await read_photo(image, cfg)
    check_rate_limit("seg:" + (request.client.host if request.client else "unknown"), cfg["seg_rate_per_hour"])
    acquire_seg_slot(cfg["seg_concurrent"])
    started = time.monotonic()
    try:
        zmap = await run_in_threadpool(seg.segment, img)
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("Fallo en la segmentación")
        raise ApiError(503, "segmentation_unavailable", "No se pudieron detectar las zonas ahora mismo. Puedes transformar la foto entera.") from exc
    finally:
        release_seg_slot()
        log.info("segment size=%sx%s seconds=%.1f", img.width, img.height, time.monotonic() - started)
    buf = io.BytesIO()
    seg.map_to_png(zmap).save(buf, format="PNG", optimize=True)
    return JSONResponse(
        {
            "width": img.width,
            "height": img.height,
            "step": seg.MAP_STEP,
            "zones": seg.zones_summary(zmap),
            "map": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/style")
async def detect_style(request: Request, image: UploadFile = File(...)):
    """Detecta el estilo actual de la habitación (CLIP zero-shot, en el propio
    servicio). No guarda nada. Si el modelo duda o la foto no muestra una
    estancia con muebles, devuelve suggest=false y un motivo."""
    from starlette.concurrency import run_in_threadpool

    cfg = settings()
    img = await read_photo(image, cfg)
    check_rate_limit("style:" + (request.client.host if request.client else "unknown"), cfg["style_rate_per_hour"])
    # Comparte los huecos de CPU con la segmentación: ambas corren en este servicio.
    acquire_seg_slot(cfg["seg_concurrent"])
    started = time.monotonic()
    try:
        result = await run_in_threadpool(style_mod.classify, img)
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("Fallo en la detección de estilo")
        raise ApiError(503, "style_unavailable", "No se pudo detectar el estilo ahora mismo.") from exc
    finally:
        release_seg_slot()
        log.info("style seconds=%.1f", time.monotonic() - started)
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@app.post("/api/renovate")
async def renovate(
    request: Request,
    image: UploadFile = File(...),
    style: str = Form(...),
    strength: float = Form(0.55),
    mask: UploadFile | None = File(None),
    zones: str = Form(""),
    variants: int = Form(1),
):
    cfg = settings()
    n = min(max(1, variants), max(1, cfg["variants_max"]))
    if not cfg["token"]:
        raise ApiError(503, "not_configured", "El servicio de IA no está configurado (falta HF_TOKEN en el servidor).")
    style = clean_style(style)
    strength = min(0.8, max(0.3, strength))
    zone_list = parse_zones(zones)

    img = await read_photo(image, cfg)
    mask_arr = None
    if mask is not None:
        mask_bytes = await mask.read(2 * 1024 * 1024 + 1)
        if len(mask_bytes) > 2 * 1024 * 1024:
            raise ApiError(413, "invalid_mask", "La selección de zonas es demasiado grande.")
        mask_arr = read_mask(mask_bytes, img.size)
    prompt = build_prompt(style, zone_list if mask_arr is not None else [])

    client_id = request.client.host if request.client else "unknown"
    check_rate_limit(client_id, cfg["rate_per_hour"], weight=n)
    acquire_slot(cfg["max_concurrent"])
    started = time.monotonic()
    try:
        # generate() es bloqueante (HTTP síncrono): se ejecuta en un hilo para
        # no parar el bucle de eventos mientras el modelo trabaja.
        from starlette.concurrency import run_in_threadpool

        if n == 1:
            # Una sola variante: sin puntuar (ahorra CPU), respuesta JPEG como siempre.
            result = await run_in_threadpool(generate, img, prompt, strength, cfg)
            if mask_arr is not None:
                result = seg.composite(img, result, mask_arr)
            body = to_jpeg(result)
        else:
            found, error = await run_in_threadpool(generate_variants, img, prompt, strength, cfg, n, mask_arr)
            if not found:
                raise error
            judge(found, cfg)
            retried = False
            if all(v["discarded"] for v in found):
                # Todas por debajo del umbral: un reintento (consume cupo) y se
                # muestra la mejor disponible de todas.
                try:
                    check_rate_limit(client_id, cfg["rate_per_hour"], weight=n)
                    more, _ = await run_in_threadpool(generate_variants, img, prompt, strength, cfg, n, mask_arr)
                    judge(more, cfg)
                    found += more
                    retried = True
                except ApiError:
                    pass  # sin cupo o crédito para reintentar: se muestra la mejor que hay
            best = pick_best(found)
            payload = {
                "best": best,
                "retried": retried,
                "low_quality": found[best]["discarded"],
                "variants": [
                    {"image": "data:image/jpeg;base64," + base64.b64encode(to_jpeg(v["image"])).decode(),
                     **{k: v.get(k) for k in ("score", "aesthetic", "realism", "change", "discarded", "reason")}}
                    for v in found
                ],
            }
    finally:
        release_slot()
        # Solo métricas, nunca la foto, la máscara ni el texto del usuario.
        log.info("renovate size=%sx%s strength=%.2f masked=%s variants=%s seconds=%.1f", img.width, img.height,
                 strength, mask_arr is not None, n, time.monotonic() - started)
    if n == 1:
        return Response(body, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})
