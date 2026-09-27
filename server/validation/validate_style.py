"""Valida la detección de estilo (CLIP zero-shot) ANTES de integrarla.

Descarga fotos de interiores de estilos conocidos (Wikimedia Commons, licencia
libre, solo fotos de cámara), las clasifica con CLIP en modo zero-shot contra
una lista de estilos, y compara dos modelos (base/32 y large/14). El estilo
"esperado" es el de la búsqueda: es una etiqueta aproximada, no una verdad
absoluta, así que el informe incluye cada foto para revisarla a ojo.

Salida en results_style/: NN.jpg (foto + top-3 de cada modelo) y report.md.
"""

from __future__ import annotations

import json
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageOps

import validate_segmentation as v

MODELS = {"base32": "openai/clip-vit-base-patch32", "large14": "openai/clip-vit-large-patch14"}
# Etiqueta interna -> (nombre en español, texto para CLIP)
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
TEMPLATE = "a photo of {}"
# Búsqueda -> estilo esperado ("?" = caso difícil sin estilo claro)
SEARCHES = [
    ("filetype:bitmap rustic interior wooden beams", "rustico"),
    ("filetype:bitmap scandinavian interior design", "escandinavo"),
    ("filetype:bitmap industrial loft apartment", "industrial"),
    ("filetype:bitmap minimalist interior", "minimalista"),
    ("filetype:bitmap bohemian interior", "bohemio"),
    ("filetype:bitmap classic interior salon chandelier", "clasico"),
    ("filetype:bitmap modern apartment interior", "moderno"),
    ("filetype:bitmap empty apartment room", "?"),
    ("filetype:bitmap dark room interior night", "?"),
]
OUT = v.HERE / "results_style"


class Clip:
    def __init__(self, model_id: str):
        import torch
        from transformers import CLIPModel, CLIPProcessor

        self.torch = torch
        self.model = CLIPModel.from_pretrained(model_id).eval()
        self.proc = CLIPProcessor.from_pretrained(model_id)
        texts = [TEMPLATE.format(t) for _, t in STYLES.values()]
        with torch.no_grad():
            t = self.proc(text=texts, return_tensors="pt", padding=True)
            self.text = torch.nn.functional.normalize(self.model.get_text_features(**t), dim=-1)

    def __call__(self, img: Image.Image) -> np.ndarray:
        torch = self.torch
        with torch.no_grad():
            i = self.proc(images=img, return_tensors="pt")
            f = torch.nn.functional.normalize(self.model.get_image_features(**i), dim=-1)
            logits = self.model.logit_scale.exp() * f @ self.text.T
            return logits.softmax(dim=-1)[0].numpy()


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for old in OUT.iterdir():
        old.unlink()
    photos = []
    for query, expected in SEARCHES:
        v.QUERIES, v.PER_QUERY = [query], 2
        for ph in v.fetch_commons(max_total=2):
            if any(ph["title"] == other["title"] for other in photos):
                continue  # la misma foto puede salir en dos búsquedas
            ph["expected"] = expected
            photos.append(ph)
    keys = list(STYLES)
    results = {}
    for name, mid in MODELS.items():
        clip = Clip(mid)
        rows = []
        for ph in photos:
            img = ImageOps.exif_transpose(ph["image"]).convert("RGB")
            t0 = time.perf_counter()
            probs = clip(img)
            rows.append((probs, time.perf_counter() - t0))
        results[name] = rows
    lines = ["# Validación de la detección de estilo (CLIP zero-shot)", "",
             "Estilo esperado = el de la búsqueda (aproximado; revisar las fotos). "
             "`?` = caso difícil sin estilo claro (habitación vacía, poca luz).",
             "Celda: top-1 (probabilidad) · margen sobre el 2.º.", "",
             "| # | Esperado | " + " | ".join(MODELS) + " |", "|---|---|" + "---|" * len(MODELS)]
    summary = []
    for n, ph in enumerate(photos, 1):
        cells, entry = [], {"n": n, "title": ph["title"], "expected": ph["expected"], "models": {}}
        for name in MODELS:
            probs, dt = results[name][n - 1]
            order = np.argsort(-probs)
            top, second = keys[order[0]], keys[order[1]]
            margin = float(probs[order[0]] - probs[order[1]])
            ok = "✅" if top == ph["expected"] else ("·" if ph["expected"] == "?" else "❌")
            cells.append(f"{ok} {STYLES[top][0]} ({probs[order[0]]:.2f}) · +{margin:.2f}")
            entry["models"][name] = {"top3": [[keys[i], round(float(probs[i]), 3)] for i in order[:3]], "margin": round(margin, 3), "seconds": round(dt, 2)}
        summary.append(entry)
        lines.append(f"| {n} | {STYLES[ph['expected']][0] if ph['expected'] != '?' else '?'} | " + " | ".join(cells) + " |")
        img = ImageOps.exif_transpose(ph["image"]).convert("RGB")
        img.thumbnail((640, 640))
        canvas = Image.new("RGB", (img.width, img.height + 16 * (1 + 3 * len(MODELS))), "white")
        canvas.paste(img, (0, 0))
        d = ImageDraw.Draw(canvas)
        y = img.height + 2
        d.text((4, y), f"esperado: {ph['expected']}", fill=(0, 0, 0))
        for name in MODELS:
            for k, p in entry["models"][name]["top3"]:
                y += 16
                d.text((4, y), f"{name}: {STYLES[k][0]} {p:.2f}", fill=(0, 0, 0))
        canvas.save(OUT / f"{n:02d}.jpg", quality=85)
    # Aciertos y calibración: ¿qué umbral de confianza separa aciertos de fallos?
    lines += ["", "## Resumen", "", "| Modelo | Aciertos (fotos con estilo esperado) | Tiempo medio/foto |", "|---|---|---|"]
    labelled = [s for s in summary if s["expected"] != "?"]
    for name in MODELS:
        hits = sum(s["models"][name]["top3"][0][0] == s["expected"] for s in labelled)
        t = np.mean([results[name][i][1] for i in range(len(photos))])
        lines.append(f"| {name} | {hits}/{len(labelled)} | {t:.2f} s |")
    lines += ["", "## Umbral de confianza (top-1 ≥ p y margen ≥ m)", "",
              "| Modelo | p | m | Se mostraría en | Aciertos entre las mostradas |", "|---|---|---|---|---|"]
    for name in MODELS:
        for p in (0.3, 0.4, 0.5, 0.6):
            for m in (0.1, 0.2):
                shown = [s for s in labelled if s["models"][name]["top3"][0][1] >= p and s["models"][name]["margin"] >= m]
                hits = sum(s["models"][name]["top3"][0][0] == s["expected"] for s in shown)
                lines.append(f"| {name} | {p} | {m} | {len(shown)}/{len(labelled)} | {hits}/{len(shown) if shown else 0} |")
    lines += ["", *[f"![{s['n']:02d}]({s['n']:02d}.jpg)" for s in summary], "", "## Atribución", "",
              *[f"- {n:02d}: [{ph['title']}]({ph['source']}) — {ph['artist']}, {ph['license']}" for n, ph in enumerate(photos, 1)]]
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(lines[:40]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
