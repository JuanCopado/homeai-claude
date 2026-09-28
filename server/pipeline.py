"""Lógica del pipeline de generación que no depende de FastAPI.

La usan el servidor (app.py) y el notebook de Colab
(validation/colab/build_notebook.py lo incrusta tal cual), así que la medición
de QA ejecuta exactamente el mismo código que producción:

    prompt -> N variantes -> filtro de similitud (casi idénticas al original:
    descartar y regenerar una vez) -> puntuador estético solo sobre las que
    pasan -> umbral de calidad -> la mejor

Modelo: Qwen/Qwen-Image-Edit (Apache-2.0). Es un modelo de EDICIÓN por
instrucciones, no un img2img tipo SDXL: el texto lo lee Qwen2.5-VL viendo la
foto (semántica) y el VAE aporta la apariencia de la foto original. Por eso
el prompt es una instrucción ("Redecora esta habitación...") y no una lista
de etiquetas, y no existe "strength": la intensidad del cambio se pide en la
propia instrucción.
"""

from __future__ import annotations

import numpy as np

import segmentation as seg

# --- Prompts -----------------------------------------------------------------

# Modelos img2img clásicos (SDXL y similares): prompt descriptivo + strength.
STRUCTURE_SUFFIX = (
    "same room, same camera angle, keep walls, windows, doors, ceiling and floor layout "
    "exactly in place, realistic interior design photograph, natural light, high detail"
)
DEFAULT_NEGATIVE = (
    "different room, changed layout, moved windows, extra doors, distorted walls, "
    "warped perspective, people, text, watermark, blurry, low quality, cartoon"
)

# Modelos de edición por instrucciones (Qwen-Image-Edit, FLUX Kontext...).
EDIT_KEEP = (
    "Keep the same room and the same camera angle: walls, windows, doors, ceiling height and floor layout "
    "stay exactly where they are. The result must look like a real, photorealistic interior photograph "
    "with natural light."
)
# strength (0,30-0,80 en la interfaz) -> cuánto se pide cambiar.
EDIT_INTENSITY = [
    (0.45, "Make a subtle update: change only colours, textiles, lighting and decoration, keep the existing furniture."),
    (0.65, "Replace the furniture, finishes and decoration to match this style."),
    (1.01, "Do a complete redesign of furniture, finishes, lighting and decoration in this style."),
]


def is_edit_model(model: str) -> bool:
    m = model.lower()
    return any(k in m for k in ("image-edit", "kontext", "instruct")) or (m.startswith("http") and "edit" in m)


def build_prompt(style: str, zones: list[str], strength: float = 0.55, edit: bool = False) -> str:
    if not edit:
        if not zones:
            return f"{style}, {STRUCTURE_SUFFIX}"
        target = " and ".join(seg.ZONE_PROMPT[z] for z in zones)
        return f"{target} redesigned: {style}, {STRUCTURE_SUFFIX}"
    intensity = next(text for limit, text in EDIT_INTENSITY if strength < limit)
    if zones:
        target = " and ".join(seg.ZONE_PROMPT[z] for z in zones)
        head = f"Redesign only {target} of this room in this style: {style}. Leave everything else unchanged."
    else:
        head = f"Redecorate this room in this style: {style}."
    return f"{head} {intensity} {EDIT_KEEP}"


# --- Filtro de similitud, puntuación y elección ------------------------------

def zone_box(mask_arr, size, pad: int = 8):
    """Caja de la zona elegida (+pad) donde se mide la similitud."""
    if mask_arr is None:
        return None
    ys, xs = np.nonzero(mask_arr)
    w, h = size
    return (max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad),
            min(w, int(xs.max()) + pad + 1), min(h, int(ys.max()) + pad + 1))


def check_similarity(variants: list[dict], original, box, max_similarity: float) -> bool:
    """Paso 1, ANTES del puntuador: marca como descartadas («sin_cambios») las
    variantes casi idénticas al original. Devuelve False si no se pudo medir
    (sin CLIP): entonces no se descarta nada."""
    import quality

    try:
        for v in variants:
            v["similarity"] = quality.similarity(v["image"], original, box)
    except Exception:  # noqa: BLE001 - sin modelo se sigue sin filtrar
        return False
    for v in variants:
        near = v["similarity"] > max_similarity
        v["discarded"], v["reason"] = near, ("sin_cambios" if near else None)
    return True


def score_variants(variants: list[dict], min_score: float) -> bool:
    """Paso 2: puntuador estético SOLO sobre las que pasaron el filtro de
    similitud; las de nota baja se marcan «calidad_baja». Devuelve False si el
    puntuador falla (se devuelven sin filtrar por calidad)."""
    import quality

    kept = [v for v in variants if not v.get("discarded")]
    try:
        for v in kept:
            v.update(quality.score(v["image"]))
    except Exception:  # noqa: BLE001
        return False
    for v in kept:
        if v["score"] < min_score:
            v["discarded"], v["reason"] = True, "calidad_baja"
    return True


def pick_best(variants: list[dict]) -> int:
    """La de más nota entre las no descartadas. Si todas lo están, antes una de
    «calidad baja» que una «sin cambios» (mostrar la foto tal cual no sirve), y
    entre las «sin cambios», la que menos se parece al original."""

    def key(i):
        v = variants[i]
        if v.get("reason") == "sin_cambios":
            return (2, v.get("similarity") if v.get("similarity") is not None else 1.0)
        return (1 if v.get("reason") else 0, -(v.get("score") or 0))

    return min(range(len(variants)), key=key)
