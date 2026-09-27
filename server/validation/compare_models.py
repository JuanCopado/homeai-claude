"""Ronda 3: compara SegFormer b0 / b2 / b4 (ADE20K) sobre las MISMAS fotos de la
ronda 2 (se cargan por su título exacto en Wikimedia Commons, leído de
results/summary.json) y mide el tiempo por foto en CPU.

Salida en results_compare/: NN.jpg (original | b0 | b2 | b4) y compare.md.
"""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageOps

import validate_segmentation as v

MODELS = {
    "b0": "nvidia/segformer-b0-finetuned-ade-512-512",
    "b2": "nvidia/segformer-b2-finetuned-ade-512-512",
    "b4": "nvidia/segformer-b4-finetuned-ade-512-512",
}
OUT = v.HERE / "results_compare"
PANEL = 640


def fetch_by_title(title: str) -> Image.Image:
    params = {"action": "query", "format": "json", "titles": title, "prop": "imageinfo",
              "iiprop": "url", "iiurlwidth": 1280}
    pages = requests.get("https://commons.wikimedia.org/w/api.php", params=params, headers=v.UA, timeout=30).json()["query"]["pages"]
    info = next(iter(pages.values()))["imageinfo"][0]
    raw = requests.get(info.get("thumburl") or info["url"], headers=v.UA, timeout=60).content
    img = Image.open(io.BytesIO(raw))
    img.load()
    return img


def panel(img: Image.Image, zmap: np.ndarray | None, title: str) -> Image.Image:
    if zmap is not None:
        palette = np.array([v.COLORS[z] for z in v.ZONE_ORDER], dtype=np.uint8)
        img = Image.blend(img, Image.fromarray(palette[zmap]), 0.55)
    img = img.copy()
    img.thumbnail((PANEL, PANEL))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 8 + 7 * len(title), 18), fill=(255, 255, 255))
    d.text((4, 3), title, fill=(0, 0, 0))
    return img


def main() -> int:
    summary = json.loads((v.OUT / "summary.json").read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    for old in OUT.iterdir():
        old.unlink()
    photos = []
    for s in summary:
        try:
            img = ImageOps.exif_transpose(fetch_by_title(s["title"])).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            print(f"[aviso] no se pudo descargar {s['title']}: {exc}")
            continue
        img.thumbnail((1024, 1024))
        photos.append((s, img))

    results = {name: [] for name in MODELS}  # por modelo: lista de (stats, zmap, segundos)
    for name, model_id in MODELS.items():
        seg = v.Segmenter(model_id)
        seg(photos[0][1])  # calentamiento: no cuenta en el tiempo
        for s, img in photos:
            t0 = time.perf_counter()
            labels, conf = seg(img)
            dt = time.perf_counter() - t0
            zmap = v.zone_map(labels, seg.id2label)
            results[name].append((v.analyse(zmap, conf, labels, seg.id2label), zmap, dt))
            print(f"{name} {s['n']:02d} {dt:.2f}s")

    lines = [
        "# Ronda 3: SegFormer b0 vs b2 vs b4",
        "",
        "Mismas 10 fotos que la ronda 2. Cada imagen: original | b0 | b2 | b4.",
        "Celdas: % de la foto (confianza media). Tiempo: segundos por foto en la CPU del runner de GitHub (2 núcleos).",
        "",
        "## Resumen por modelo",
        "",
        "| Modelo | Tiempo medio/foto | Confianza media pared | suelo | techo | ventana/puerta | mobiliario |",
        "|---|---|---|---|---|---|---|",
    ]
    for name in MODELS:
        rs = results[name]
        t = sum(r[2] for r in rs) / len(rs)
        confs = []
        for z in v.ZONES:
            vals = [r[0][z]["conf"] for r in rs if r[0][z]["conf"] is not None and r[0][z]["pct"] > 1]
            confs.append(f"{sum(vals) / len(vals):.2f}" if vals else "-")
        lines.append(f"| {name} | {t:.2f} s | " + " | ".join(confs) + " |")
    lines += ["", "## Por foto", "", "| # | Tipo | Modelo | " + " | ".join(v.ZONE_ORDER) + " |",
              "|---|---|---|" + "---|" * len(v.ZONE_ORDER)]
    for i, (s, img) in enumerate(photos):
        panels = [panel(img, None, "original")] + [panel(img, results[m][i][1], m) for m in MODELS]
        w = sum(p.width for p in panels)
        canvas = Image.new("RGB", (w, panels[0].height), "white")
        x = 0
        for p in panels:
            canvas.paste(p, (x, 0))
            x += p.width
        canvas.save(OUT / f"{s['n']:02d}.jpg", quality=85)
        for m in MODELS:
            st = results[m][i][0]
            cells = " | ".join(f"{st[z]['pct']}% ({st[z]['conf'] if st[z]['conf'] is not None else '-'})" for z in v.ZONE_ORDER)
            lines.append(f"| {s['n']} | {s['query']} | {m} | {cells} |")
    lines += ["", *[f"![{s['n']:02d}]({s['n']:02d}.jpg)" for s, _ in photos], ""]
    (OUT / "compare.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(photos)} fotos comparadas. Informe: {OUT / 'compare.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
