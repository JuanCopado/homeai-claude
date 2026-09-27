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

import io
import logging
import os
import re
import threading
import time
from collections import defaultdict, deque

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError
from starlette.formparsers import MultiPartParser

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
        "model": os.environ.get("HF_MODEL", "stabilityai/stable-diffusion-xl-base-1.0"),
        "provider": os.environ.get("HF_PROVIDER", "auto"),
        "timeout": env_float("HF_TIMEOUT_SECONDS", 120),
        "max_upload": env_int("MAX_UPLOAD_MB", 10) * 1024 * 1024,
        "max_side": env_int("MAX_IMAGE_SIDE", 1024),
        "steps": env_int("HF_STEPS", 30),
        "guidance": env_float("HF_GUIDANCE_SCALE", 7.0),
        "rate_per_hour": env_int("RATE_LIMIT_PER_HOUR", 10),
        "max_concurrent": env_int("MAX_CONCURRENT_GENERATIONS", 2),
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


def check_rate_limit(client_id: str, per_hour: int) -> None:
    if per_hour <= 0:
        return
    now = time.monotonic()
    with _hits_lock:
        q = _hits[client_id]
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= per_hour:
            retry = int(3600 - (now - q[0])) + 1
            raise ApiError(429, "rate_limited", "Has alcanzado el límite de visualizaciones por hora. Prueba más tarde.", retry)
        q.append(now)


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


def generate(img: Image.Image, style: str, strength: float, cfg: dict) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    client = make_client(cfg)
    try:
        result = client.image_to_image(
            buf.getvalue(),
            prompt=f"{style}, {STRUCTURE_SUFFIX}",
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
    out = io.BytesIO()
    result.convert("RGB").save(out, format="JPEG", quality=90)
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
    if request.method == "POST" and request.url.path == "/api/renovate":
        limit = settings()["max_upload"] + 64 * 1024  # margen para el resto del formulario
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


@app.post("/api/renovate")
async def renovate(request: Request, image: UploadFile = File(...), style: str = Form(...), strength: float = Form(0.55)):
    cfg = settings()
    if not cfg["token"]:
        raise ApiError(503, "not_configured", "El servicio de IA no está configurado (falta HF_TOKEN en el servidor).")
    style = clean_style(style)
    strength = min(0.8, max(0.3, strength))

    data = await image.read(cfg["max_upload"] + 1)
    if len(data) > cfg["max_upload"]:
        raise ApiError(413, "image_too_large", f"La foto pesa demasiado (máximo {cfg['max_upload'] // (1024 * 1024)} MB).")
    img = preprocess(data, cfg["max_side"])
    del data

    check_rate_limit(request.client.host if request.client else "unknown", cfg["rate_per_hour"])
    acquire_slot(cfg["max_concurrent"])
    started = time.monotonic()
    try:
        # generate() es bloqueante (HTTP síncrono): se ejecuta en un hilo para
        # no parar el bucle de eventos mientras el modelo trabaja.
        from starlette.concurrency import run_in_threadpool

        body = await run_in_threadpool(generate, img, style, strength, cfg)
    finally:
        release_slot()
        # Solo métricas, nunca la foto ni el texto del usuario.
        log.info("renovate size=%sx%s strength=%.2f seconds=%.1f", img.width, img.height, strength, time.monotonic() - started)
    return Response(body, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
