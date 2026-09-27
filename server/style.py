"""Detección automática del estilo actual de la habitación (CLIP zero-shot).

Elegido tras validarlo con fotos reales (server/validation/validate_style.py,
results_style/report.md y CURRENT_STATE.md):
- openai/clip-vit-large-patch14: 6/7 aciertos en fotos de estilo claro frente
  a 3-4/8 de base/32.
- Solo se sugiere si la probabilidad del primero es >= 0,5 y le saca >= 0,2
  al segundo: con eso, las sugerencias mostradas acertaron 6/6.
- Etiquetas "sumidero" (habitación vacía, primer plano de un objeto, exterior):
  si ganan, no se sugiere nada. Sin ellas, una habitación vacía salía
  "minimalista" con 0,97.
- Sin validar con fotos buenas: escandinavo, bohemio y mediterráneo.

torch/transformers se importan solo al cargar el modelo.
"""

from __future__ import annotations

import os
import threading

from PIL import Image

STYLE_MODEL = os.environ.get("STYLE_MODEL", "openai/clip-vit-large-patch14")
MIN_PROB = float(os.environ.get("STYLE_MIN_PROB", 0.5))
MIN_MARGIN = float(os.environ.get("STYLE_MIN_MARGIN", 0.2))

# clave -> (nombre para mostrar, texto para CLIP). Mismas frases que en la validación.
STYLES = {
    "moderno": ("Moderno", "a modern contemporary interior"),
    "rustico": ("Rústico", "a rustic interior with exposed wood beams and stone"),
    "minimalista": ("Minimalista", "a minimalist interior with very few objects"),
    "industrial": ("Industrial", "an industrial loft interior with exposed brick, concrete and metal"),
    "escandinavo": ("Escandinavo", "a scandinavian interior with white walls and light wood"),
    "clasico": ("Clásico", "a classic traditional interior with ornate furniture and moldings"),
    "bohemio": ("Bohemio", "a bohemian interior with plants, rugs and colorful patterns"),
    "mediterraneo": ("Mediterráneo", "a mediterranean interior with whitewashed walls and terracotta"),
}
SINKS = {
    "vacia": "an empty unfurnished room with bare walls",
    "objeto": "a close-up photo of a single object or piece of furniture",
    "exterior": "the outside of a building seen from the street or garden",
}
SINK_REASON = {
    "vacia": "La habitación parece vacía: no hay muebles que indiquen un estilo.",
    "objeto": "La foto parece un detalle de cerca, no la estancia entera.",
    "exterior": "La foto parece el exterior de un edificio.",
}
KEYS = list(STYLES) + list(SINKS)
TEMPLATE = "a photo of {}"


class _Clip:
    def __init__(self, model_id: str):
        import torch
        from transformers import CLIPModel, CLIPProcessor

        torch.set_num_threads(max(1, os.cpu_count() or 1))
        self.torch = torch
        self.model = CLIPModel.from_pretrained(model_id).eval()
        self.proc = CLIPProcessor.from_pretrained(model_id)
        self.texts = [TEMPLATE.format(t) for _, t in STYLES.values()] + [TEMPLATE.format(t) for t in SINKS.values()]

    def __call__(self, img: Image.Image) -> list[float]:
        # logits_per_image: salida estable entre versiones de transformers.
        with self.torch.no_grad():
            inputs = self.proc(text=self.texts, images=img, return_tensors="pt", padding=True)
            return self.model(**inputs).logits_per_image.softmax(dim=-1)[0].tolist()


_clip = None
_clip_lock = threading.Lock()


def load_classifier():
    global _clip
    with _clip_lock:
        if _clip is None:
            _clip = _Clip(STYLE_MODEL)
    return _clip


def decide(probs: list[float]) -> dict:
    """Convierte las probabilidades en la respuesta de la API.

    suggest=False cuando gana una etiqueta sumidero o el modelo duda (poca
    probabilidad o poca ventaja sobre el segundo). En ese caso la interfaz no
    muestra ningún estilo como detectado.
    """
    ranked = sorted(zip(KEYS, probs), key=lambda kv: -kv[1])
    (top, p1), (_, p2) = ranked[0], ranked[1]
    styles_only = [(k, p) for k, p in ranked if k in STYLES][:3]
    result = {
        "style": None,
        "label": None,
        "confidence": round(p1, 3),
        "margin": round(p1 - p2, 3),
        "suggest": False,
        "reason": None,
        "top": [{"style": k, "label": STYLES[k][0], "p": round(p, 3)} for k, p in styles_only],
    }
    if top in SINKS:
        result["reason"] = SINK_REASON[top]
    elif p1 < MIN_PROB or p1 - p2 < MIN_MARGIN:
        result["reason"] = "No hay un estilo claro en la foto (o mezcla varios)."
    else:
        result.update(style=top, label=STYLES[top][0], suggest=True)
    return result


def classify(img: Image.Image) -> dict:
    return decide(load_classifier()(img))
