"""Descarga las fotos de prueba (Wikimedia Commons, licencia libre).

- single/: 2 fotos de pisos de la validación de segmentación (salón al
  atardecer y cocina estrecha).
- multi/: varias fotos de la MISMA estancia (serie «Interior of apartment in
  Brisbane, 2025», CC BY-SA 4.0), para los métodos multi-vista.
"""

import io
import json
import re
import sys
from pathlib import Path

import requests
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).parent.parent))
from common_fetch import UA, by_title  # noqa: E402
from r3d.common import INPUT  # noqa: E402

HERE = Path(__file__).parent.parent


def save(img: Image.Image, path: Path):
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((1024, 1024))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, quality=92)


def main():
    credits = []
    summary = {s["n"]: s for s in json.loads((HERE / "results" / "summary.json").read_text(encoding="utf-8"))}
    for n in (1, 4):
        img, meta = by_title(summary[n]["title"])
        save(img, INPUT / "single" / f"{n:02d}.jpg")
        credits.append(meta)
    params = {"action": "query", "format": "json", "list": "search", "srnamespace": 6, "srlimit": 50,
              "srsearch": 'intitle:"Interior of apartment in Brisbane, 2025"'}
    titles = [r["title"] for r in requests.get("https://commons.wikimedia.org/w/api.php", params=params, headers=UA, timeout=30).json()["query"]["search"]]
    print("Serie Brisbane:", titles)
    bedroom = sorted(t for t in titles if re.search(r"bedroom", t, re.I))
    living = sorted(t for t in titles if re.search(r"living|lounge", t, re.I))
    chosen = bedroom if len(bedroom) >= 3 else (living if len(living) >= 3 else sorted(titles)[:4])
    for i, t in enumerate(chosen[:5], 1):
        img, meta = by_title(t)
        save(img, INPUT / "multi" / f"{i:02d}.jpg")
        credits.append(meta)
    (INPUT / "credits.json").write_text(json.dumps(credits, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(credits, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
