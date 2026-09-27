"""Puntuación de calidad de las imágenes generadas (para elegir la mejor variante).

Dos señales sobre el mismo CLIP large/14 que ya usa la detección de estilo
(style.py), así que no se carga otro modelo grande:

- aesthetic: predictor estético de LAION ("improved-aesthetic-predictor",
  Christoph Schuhmann, Apache-2.0): una MLP pequeña sobre el embedding de
  imagen de CLIP ViT-L/14, entrenada con valoraciones humanas (escala ~1-10).
- realism: CLIP zero-shot, probabilidad de "foto nítida y realista de una
  habitación" frente a "imagen distorsionada, borrosa o con artefactos" (0-1).

- change (solo si se pasa el original): 1 - similitud coseno entre los
  embeddings CLIP de la variante y del original. Detecta variantes en las que
  el modelo "no hizo nada": la diferencia de píxeles no sirve (una variante
  solo más luminosa movía 44 niveles de media, casi como una reforma real).

score = aesthetic normalizada (0-1) * 0,5 + realism * 0,5. Umbrales de
descarte calibrados en server/validation/check_quality.py.
"""

from __future__ import annotations

import os
import threading

from PIL import Image

import style

AESTHETIC_URL = os.environ.get(
    "AESTHETIC_WEIGHTS_URL",
    "https://github.com/christophschuhmann/improved-aesthetic-predictor/raw/main/sac+logos+ava1-l14-linearMSE.pth",
)
GOOD = "a sharp, realistic, well lit photo of a room interior"
BAD = ["a distorted, warped image with visual artifacts", "a blurry, noisy, low quality image",
       "an image with melted furniture and impossible geometry"]


class _Scorer:
    def __init__(self):
        import io

        import requests
        import torch

        self.torch = torch
        clip = style.load_classifier()  # reutiliza CLIP large/14 ya cargado
        self.model, self.proc = clip.model, clip.proc
        layers = [torch.nn.Linear(768, 1024), torch.nn.Dropout(0.2), torch.nn.Linear(1024, 128), torch.nn.Dropout(0.2),
                  torch.nn.Linear(128, 64), torch.nn.Dropout(0.1), torch.nn.Linear(64, 16), torch.nn.Linear(16, 1)]
        self.mlp = torch.nn.Sequential(*layers)
        raw = requests.get(AESTHETIC_URL, timeout=60).content
        state = torch.load(io.BytesIO(raw), map_location="cpu", weights_only=True)  # solo tensores, sin pickle de código
        self.mlp.load_state_dict({k.replace("layers.", ""): v for k, v in state.items()})
        self.mlp.eval()
        self.texts = [GOOD] + BAD

    def embed(self, img: Image.Image):
        # Embedding de imagen por las capas explícitas: estable entre versiones
        # de transformers (get_image_features cambió de tipo de retorno).
        torch = self.torch
        with torch.no_grad():
            pix = self.proc(images=img.convert("RGB"), return_tensors="pt")["pixel_values"]
            pooled = self.model.vision_model(pixel_values=pix).pooler_output
            return torch.nn.functional.normalize(self.model.visual_projection(pooled), dim=-1)

    def __call__(self, img: Image.Image, original: Image.Image | None = None) -> dict:
        torch = self.torch
        with torch.no_grad():
            emb = self.embed(img)
            aesthetic = float(self.mlp(emb)[0, 0])
            inputs = self.proc(text=self.texts, images=img.convert("RGB"), return_tensors="pt", padding=True)
            realism = float(self.model(**inputs).logits_per_image.softmax(dim=-1)[0][0])
            change = None if original is None else float(1 - (emb @ self.embed(original).T)[0, 0])
        a_norm = min(1.0, max(0.0, (aesthetic - 3.0) / 4.0))  # ~3 → 0, ~7 → 1
        out = {"aesthetic": round(aesthetic, 3), "realism": round(realism, 3), "score": round(0.5 * a_norm + 0.5 * realism, 3)}
        if change is not None:
            out["change"] = round(change, 4)
        return out


_scorer = None
_lock = threading.Lock()


def load_scorer():
    global _scorer
    with _lock:
        if _scorer is None:
            _scorer = _Scorer()
    return _scorer


def score(img: Image.Image, original: Image.Image | None = None) -> dict:
    return load_scorer()(img, original)
