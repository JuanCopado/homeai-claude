"""Segmentación por zonas y composición con máscara.

- segment(): SegFormer (ADE20K) ejecutado dentro del servicio. Se eligió b4
  tras validarlo con 10 fotos reales frente a b0/b2 (ver
  server/validation/results_compare/compare.md y CURRENT_STATE.md).
- zone_map(): agrupa las 150 clases de ADE20K en las zonas de HomeAI.
- composite(): pega el resultado del modelo SOLO dentro de la máscara. El
  borde se suaviza hacia dentro, nunca hacia fuera: fuera de la máscara la
  foto queda idéntica píxel a píxel, sirva el proveedor inpainting o no.

torch/transformers se importan solo al cargar el modelo, para que el resto
del servicio (y los tests) no dependan de ellos.
"""

from __future__ import annotations

import os
import threading

import numpy as np
from PIL import Image, ImageFilter

SEG_MODEL = os.environ.get("SEG_MODEL", "nvidia/segformer-b4-finetuned-ade-512-512")

# Orden fijo: el índice es el valor que se envía al navegador en el mapa.
ZONE_ORDER = ["pared", "suelo", "techo", "ventana/puerta", "mobiliario", "otros"]
SELECTABLE = ["pared", "suelo", "techo", "mobiliario"]
ZONE_PROMPT = {
    "pared": "the walls",
    "suelo": "the floor",
    "techo": "the ceiling",
    "ventana/puerta": "the windows and doors",
    "mobiliario": "the furniture",
    "otros": "the selected area",
}
ZONES = {
    "pared": {"wall", "column"},
    "suelo": {"floor"},
    "techo": {"ceiling"},
    "ventana/puerta": {"windowpane", "window", "door", "screen door", "double door"},
    # "mirror" queda fuera a propósito: refleja paredes y techo.
    "mobiliario": {
        "bed", "cabinet", "table", "chair", "sofa", "shelf", "armchair", "seat", "desk",
        "wardrobe", "lamp", "bathtub", "cushion", "chest of drawers", "counter", "sink",
        "fireplace", "refrigerator", "pillow", "bookcase", "coffee table", "toilet",
        "countertop", "stove", "kitchen island", "swivel chair", "chandelier", "ottoman",
        "buffet", "stool", "oven", "microwave", "dishwasher", "shower", "radiator",
        "television receiver", "curtain", "blind", "rug", "painting", "plant",
        "bench", "cradle", "sconce", "hood", "washer", "towel", "vase", "clock", "light",
    },
}
# El mapa se envía como PNG en gris con este paso entre zonas, para que una
# pequeña deriva de color al decodificarlo en el navegador no cambie la zona.
MAP_STEP = 40


def norm(label: str) -> str:
    return label.strip().lower().split(",")[0].strip()


def zone_of(label: str) -> str:
    n = norm(label)
    for zone, names in ZONES.items():
        if n in names:
            return zone
    return "otros"


def zone_map(labels: np.ndarray, id2label: dict) -> np.ndarray:
    lut = np.array([ZONE_ORDER.index(zone_of(id2label[i])) for i in range(len(id2label))], dtype=np.uint8)
    return lut[labels]


class _Segmenter:
    def __init__(self, model_id: str):
        import torch
        from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor

        torch.set_num_threads(max(1, os.cpu_count() or 1))
        self.torch = torch
        self.proc = SegformerImageProcessor.from_pretrained(model_id)
        self.model = SegformerForSemanticSegmentation.from_pretrained(model_id).eval()
        self.id2label = self.model.config.id2label

    def __call__(self, img: Image.Image) -> np.ndarray:
        torch = self.torch
        with torch.no_grad():
            logits = self.model(**self.proc(images=img, return_tensors="pt")).logits
            logits = torch.nn.functional.interpolate(logits, size=img.size[::-1], mode="bilinear", align_corners=False)
            labels = logits.argmax(dim=1)[0].numpy()
        return zone_map(labels, self.id2label)


_segmenter = None
_segmenter_lock = threading.Lock()


def load_segmenter():
    """Carga perezosa y única del modelo (tarda unos segundos la primera vez)."""
    global _segmenter
    with _segmenter_lock:
        if _segmenter is None:
            _segmenter = _Segmenter(SEG_MODEL)
    return _segmenter


def segment(img: Image.Image) -> np.ndarray:
    """Devuelve un mapa HxW de índices de ZONE_ORDER, suavizado para quitar
    motas sueltas (un filtro de moda de 5 px)."""
    zmap = load_segmenter()(img)
    smooth = Image.fromarray(zmap.astype(np.uint8)).filter(ImageFilter.ModeFilter(5))
    return np.asarray(smooth, dtype=np.uint8)


def zones_summary(zmap: np.ndarray) -> list[dict]:
    total = zmap.size
    return [
        {"id": i, "zone": z, "pct": round(100 * float((zmap == i).sum()) / total, 1), "selectable": z in SELECTABLE}
        for i, z in enumerate(ZONE_ORDER)
    ]


def map_to_png(zmap: np.ndarray) -> Image.Image:
    return Image.fromarray((zmap.astype(np.uint16) * MAP_STEP).astype(np.uint8), mode="L")


def parse_mask(img: Image.Image, size: tuple[int, int]) -> np.ndarray:
    """Máscara del navegador (blanco = modificar) -> booleano al tamaño de la foto."""
    mask = img.convert("L")
    if mask.size != size:
        mask = mask.resize(size, Image.NEAREST)
    return np.asarray(mask) > 127


def composite(original: Image.Image, generated: Image.Image, mask: np.ndarray) -> Image.Image:
    """Resultado del modelo dentro de la máscara, original fuera.

    El alfa es un desenfoque de la máscara recortado por la propia máscara:
    transición suave hacia dentro del borde y exactamente 0 fuera de él.
    """
    if generated.size != original.size:
        generated = generated.resize(original.size, Image.LANCZOS)
    radius = max(2, round(max(original.size) * 0.006))
    hard = Image.fromarray((mask * 255).astype(np.uint8), mode="L")
    soft = np.asarray(hard.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32) / 255.0
    alpha = np.where(mask, np.clip((soft - 0.5) * 2, 0, 1), 0.0)
    a = alpha[..., None]
    out = np.asarray(generated.convert("RGB"), dtype=np.float32) * a + np.asarray(original, dtype=np.float32) * (1 - a)
    result = Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8))
    # Garantía explícita: fuera de la máscara, los píxeles originales tal cual.
    result.paste(original, mask=Image.fromarray(((~mask) * 255).astype(np.uint8), mode="L"))
    return result

