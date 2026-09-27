"""Qwen/Qwen-Image-Edit ejecutado con diffusers (QwenImageEditPipeline).

Dos usos, mismo código:

1. Servidor con GPU propia: GEN_BACKEND=diffusers en app.py. get_client()
   devuelve un objeto con la misma interfaz que InferenceClient.image_to_image,
   así que el resto del pipeline (filtro de similitud, puntuador) no cambia.
   Requiere requirements-gpu.txt y una GPU de 24 GB+ con QWEN_QUANT=nf4
   (o ~60 GB sin cuantizar).
2. Notebook de Colab (validation/colab/): GPU T4 gratuita de 16 GB. Ahí no
   caben a la vez el codificador de texto (Qwen2.5-VL 7B) y el transformer
   (20B), ni siquiera en 4 bits, así que se hace en dos fases: primero se
   codifican todas las instrucciones (load(parts="text") + encode()), se
   libera la GPU, y luego se generan las imágenes (load(parts="image") +
   render()).

Modelo de edición por instrucciones: el texto lo lee Qwen2.5-VL VIENDO la foto
y el VAE aporta la apariencia original, por eso la instrucción se codifica
junto con la imagen (encode recibe las dos) y no hay parámetro "strength".
La guía es true_cfg_scale (con prompt negativo); guidance_scale no se usa.

Opcional: LoRA "Lightning" (lightx2v, Apache-2.0) para generar en 8 pasos sin
CFG en vez de 30-50 pasos con CFG (unas 8-12 veces menos cómputo).
"""

from __future__ import annotations

import io
import math
import os
import random
import threading

from PIL import Image

MODEL = "Qwen/Qwen-Image-Edit"
LIGHTNING_REPO = "lightx2v/Qwen-Image-Lightning"
LIGHTNING_FILE = os.environ.get("QWEN_LIGHTNING_FILE", "Qwen-Image-Edit-Lightning-8steps-V1.0-bf16.safetensors")
# Configuración del planificador que publica lightx2v para sus LoRA.
LIGHTNING_SCHEDULER = {
    "base_image_seq_len": 256,
    "base_shift": math.log(3),
    "invert_sigmas": False,
    "max_image_seq_len": 8192,
    "max_shift": math.log(3),
    "num_train_timesteps": 1000,
    "shift": 1.0,
    "shift_terminal": None,
    "stochastic_sampling": False,
    "time_shift_type": "exponential",
    "use_beta_sigmas": False,
    "use_dynamic_shifting": True,
    "use_exponential_sigmas": False,
    "use_karras_sigmas": False,
}


def pick_dtype(name: str | None = None):
    """bf16 en GPUs que lo tienen nativo (Ampere o posterior: L4, A10G, A100);
    fp16 en las anteriores (T4 de Colab), donde bf16 es emulado y lento y la
    atención eficiente en memoria de PyTorch solo existe en fp16. diffusers
    recorta las activaciones de Qwen-Image en fp16 para que no desborden;
    measure.py comprueba igualmente que no salgan imágenes negras o NaN."""
    import torch

    name = (name or os.environ.get("QWEN_DTYPE", "auto")).lower()
    if name == "auto":
        native = torch.cuda.is_available() and torch.cuda.is_bf16_supported(including_emulation=False)
        return torch.bfloat16 if native else torch.float16
    return torch.float16 if name in ("fp16", "float16") else torch.bfloat16


def load(model: str = MODEL, parts: str = "all", quant: str = "nf4", lightning: bool = True, dtype=None,
         device: str = "cuda", components: dict | None = None):
    """parts: "all" (servidor), "text" (solo codificar) o "image" (solo generar).
    quant: "nf4" (bitsandbytes 4 bits) o "none". components: piezas ya
    construidas (tests con un modelo diminuto)."""
    from diffusers import FlowMatchEulerDiscreteScheduler, QwenImageEditPipeline

    dtype = dtype or pick_dtype()
    kw = dict(components or {})
    need_text, need_image = parts in ("all", "text"), parts in ("all", "image")
    if not need_image:
        kw.setdefault("transformer", None)
        kw.setdefault("vae", None)
    if not need_text:
        kw.setdefault("text_encoder", None)
    if quant == "nf4":
        if need_image and "transformer" not in kw:
            from diffusers import BitsAndBytesConfig, QwenImageTransformer2DModel

            q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=dtype)
            kw["transformer"] = QwenImageTransformer2DModel.from_pretrained(
                model, subfolder="transformer", quantization_config=q, torch_dtype=dtype)
        if need_text and "text_encoder" not in kw:
            from transformers import BitsAndBytesConfig, Qwen2_5_VLForConditionalGeneration

            q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=dtype)
            kw["text_encoder"] = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                model, subfolder="text_encoder", quantization_config=q, torch_dtype=dtype)
    if lightning and need_image:
        kw["scheduler"] = FlowMatchEulerDiscreteScheduler.from_config(LIGHTNING_SCHEDULER)
    if components is not None:
        pipe = QwenImageEditPipeline(**{k: kw.get(k) for k in
                                        ("scheduler", "vae", "text_encoder", "tokenizer", "processor", "transformer")})
    else:
        pipe = QwenImageEditPipeline.from_pretrained(model, torch_dtype=dtype, **kw)
    if lightning and need_image:
        pipe.load_lora_weights(LIGHTNING_REPO, weight_name=LIGHTNING_FILE)
    # Los módulos en 4 bits ya se cargan en la GPU; el resto se mueve a mano.
    for name in ("transformer", "text_encoder", "vae"):
        mod = getattr(pipe, name, None)
        if mod is not None and not _is_4bit(mod):
            mod.to(device)
    return pipe


def _is_4bit(mod) -> bool:
    return bool(getattr(mod, "is_loaded_in_4bit", False) or getattr(mod, "quantization_method", None))


def prompt_image(pipe, image: Image.Image) -> Image.Image:
    """La foto como la ve el codificador de texto (~1 MP), igual que hace
    QwenImageEditPipeline.__call__ por dentro."""
    from diffusers.pipelines.qwenimage.pipeline_qwenimage_edit import calculate_dimensions

    w, h, _ = calculate_dimensions(1024 * 1024, image.width / image.height)
    return pipe.image_processor.resize(image, h, w)


def encode(pipe, image: Image.Image, prompt: str, negative: str | None = None) -> dict:
    """Fase 1: instrucción + foto -> embeddings (se guardan en CPU)."""
    with _no_grad():
        return _encode(pipe, image, prompt, negative)


def _encode(pipe, image, prompt, negative):
    dev = pipe._execution_device
    pimg = prompt_image(pipe, image)
    pe, pm = pipe.encode_prompt(prompt=prompt, image=pimg, device=dev)
    out = {"pe": pe.cpu(), "pm": None if pm is None else pm.cpu()}
    if negative:
        ne, nm = pipe.encode_prompt(prompt=negative, image=pimg, device=dev)
        out.update(ne=ne.cpu(), nm=None if nm is None else nm.cpu())
    return out


def render(pipe, image: Image.Image, emb: dict, steps: int, true_cfg: float, seed: int) -> Image.Image:
    """Fase 2: embeddings + foto -> imagen editada."""
    with _no_grad():
        return _render(pipe, image, emb, steps, true_cfg, seed)


def _render(pipe, image, emb, steps, true_cfg, seed):
    import torch

    dev = pipe._execution_device
    dtype = pipe.transformer.dtype
    kw = dict(image=image, prompt_embeds=emb["pe"].to(dev, dtype),
              prompt_embeds_mask=None if emb["pm"] is None else emb["pm"].to(dev),
              num_inference_steps=steps, true_cfg_scale=true_cfg,
              generator=torch.Generator(device="cpu").manual_seed(seed))
    if true_cfg > 1 and emb.get("ne") is not None:
        kw.update(negative_prompt_embeds=emb["ne"].to(dev, dtype),
                  negative_prompt_embeds_mask=None if emb["nm"] is None else emb["nm"].to(dev))
    return pipe(**kw).images[0]


class LocalClient:
    """Misma interfaz que InferenceClient.image_to_image (lo que usa app.generate)."""

    def __init__(self, model: str = MODEL, pipe=None):
        self.lightning = os.environ.get("QWEN_LIGHTNING", "0") == "1"
        self.pipe = pipe or load(model, "all", quant=os.environ.get("QWEN_QUANT", "nf4"), lightning=self.lightning)
        self.lock = threading.Lock()  # una GPU: las variantes van en serie

    def image_to_image(self, image: bytes, prompt: str, negative_prompt: str | None = None,
                       num_inference_steps: int = 30, guidance_scale: float = 4.0, model: str | None = None, **_):
        src = Image.open(io.BytesIO(image)).convert("RGB")
        steps, cfg = (8, 1.0) if self.lightning else (num_inference_steps, guidance_scale)
        with self.lock:
            emb = encode(self.pipe, src, prompt, negative_prompt if cfg > 1 else None)
            return render(self.pipe, src, emb, steps, cfg, random.randrange(2**31))


def _no_grad():
    import torch

    return torch.inference_mode()


_client = None
_client_lock = threading.Lock()


def get_client(model: str = MODEL) -> LocalClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = LocalClient(model if not model.startswith("http") else MODEL)
    return _client
