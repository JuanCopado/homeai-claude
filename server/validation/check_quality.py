"""Calibra el puntuador de calidad SIN gastar crédito de generación.

1. Fallos simulados sobre 6 fotos reales de pisos (validation/results/):
   desenfoque, ruido fuerte, artefactos JPEG extremos, deformación ("warp"),
   sobreexposición. El puntuador debe dar menos nota al fallo que al original.
2. Las 3 variantes reales de FLUX Kontext de la medición (results_variants/01.jpg,
   recortadas de la rejilla): señal "change" (1 - similitud CLIP con el
   original). La variante que casi no cambió debe quedar claramente por debajo.

Salida: results_quality/report.md.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

import quality  # noqa: E402
from compare_models import fetch_by_title  # noqa: E402

OUT = HERE / "results_quality"


def degrade(img: Image.Image) -> dict[str, Image.Image]:
    w, h = img.size
    rng = np.random.default_rng(0)
    arr = np.asarray(img, dtype=np.float32)
    noisy = Image.fromarray(np.clip(arr + rng.normal(0, 45, arr.shape), 0, 255).astype(np.uint8))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=4)
    jpeg = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    ys, xs = np.mgrid[0:h, 0:w]
    dx = (18 * np.sin(ys / 23.0)).astype(int)
    dy = (18 * np.cos(xs / 29.0)).astype(int)
    warp = Image.fromarray(arr[np.clip(ys + dy, 0, h - 1), np.clip(xs + dx, 0, w - 1)].astype(np.uint8))
    over = Image.fromarray(np.clip(arr * 2.2 + 60, 0, 255).astype(np.uint8))
    return {"borrosa": img.filter(ImageFilter.GaussianBlur(8)), "ruido": noisy, "jpeg": jpeg, "deformada": warp, "quemada": over}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    summary = json.loads((HERE / "results" / "summary.json").read_text(encoding="utf-8"))
    lines = ["# Calibración del puntuador de calidad", "", "## 1. Fallos simulados (nota del fallo < nota del original)", "",
             "| Foto | Original | borrosa | ruido | jpeg | deformada | quemada |", "|---|---|---|---|---|---|---|"]
    ok = total = 0
    worst_gap = []
    for s in summary[:6]:
        img = fetch_by_title(s["title"]).convert("RGB")
        img.thumbnail((768, 768))
        base = quality.score(img)["score"]
        cells = []
        for name, bad in degrade(img).items():
            sc = quality.score(bad)["score"]
            total += 1
            ok += sc < base
            worst_gap.append(base - sc)
            cells.append(f"{sc} {'✅' if sc < base else '❌'}")
        lines.append(f"| {s['n']:02d} | {base} | " + " | ".join(cells) + " |")
    lines += ["", f"Fallos con nota menor que su original: **{ok}/{total}**; diferencia media {np.mean(worst_gap):.3f}.", ""]

    grid = Image.open(HERE / "results_variants" / "01.jpg").convert("RGB")
    W, H = grid.size
    w = W // 4
    tiles = [grid.crop((i * w, 20, (i + 1) * w, H)) for i in range(4)]
    lines += ["## 2. Variantes reales (FLUX Kontext, «estilo nórdico»)", "",
              "| Variante | A ojo | score | change (1 - similitud CLIP) |", "|---|---|---|---|"]
    eye = {1: "casi sin cambios", 2: "reforma nórdica completa", 3: "cambio intermedio"}
    for i in range(1, 4):
        sc = quality.score(tiles[i], tiles[0])
        lines.append(f"| v{i} | {eye[i]} | {sc['score']} | {sc['change']} |")
    same = quality.score(tiles[0], tiles[0])["change"]
    lines += ["", f"Referencia: original contra sí mismo, change = {same}."]
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
