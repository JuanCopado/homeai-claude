"""Comprueba el código de PRODUCCIÓN (server/app.py + server/segmentation.py)
con el modelo real SegFormer-b4, sobre fotos reales de la ronda 2:

1. /api/segment devuelve un mapa coherente (tamaño, zonas, % que suman 100).
2. /api/renovate con una máscara (suelo, y pared+mobiliario) no modifica
   nada fuera de ella: la generación se sustituye por un color plano para
   poder medirlo; lo que se prueba es la máscara y la composición reales.

Guarda en results_server/ una imagen por caso: original | zonas | resultado.
Se ejecuta en GitHub Actions (el entorno de desarrollo no llega a HF).
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("HF_TOKEN", "hf_fake_for_check")
os.environ.setdefault("RATE_LIMIT_PER_HOUR", "1000")
os.environ.setdefault("SEG_RATE_LIMIT_PER_HOUR", "1000")

from fastapi.testclient import TestClient  # noqa: E402

import app as service  # noqa: E402
import segmentation as seg  # noqa: E402
from compare_models import fetch_by_title  # noqa: E402

OUT = HERE / "results_server"


class FlatGenerator:
    def image_to_image(self, image, **kwargs):
        return Image.new("RGB", Image.open(io.BytesIO(image)).size, (0, 255, 0))


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for old in OUT.iterdir():
        old.unlink()
    service.make_client = lambda cfg: FlatGenerator()
    api = TestClient(service.app)
    summary = json.loads((HERE / "results" / "summary.json").read_text(encoding="utf-8"))
    palette = np.array([(231, 111, 81), (42, 157, 143), (233, 196, 106), (69, 123, 157), (155, 93, 229), (120, 120, 120)], np.uint8)
    report = ["# Comprobación del servidor con SegFormer-b4 real", "",
              "| Foto | Zonas (%) | Selección | Fuga fuera de la máscara (>16 px del borde) | Ruido JPEG fuera (>12 niveles) | Dentro sustituido |",
              "|---|---|---|---|---|---|"]
    failures = 0
    for s in summary[:6]:
        src = fetch_by_title(s["title"]).convert("RGB")
        src.thumbnail((1024, 1024))
        buf = io.BytesIO()
        src.save(buf, format="JPEG", quality=92)
        r = api.post("/api/segment", files={"image": ("f.jpg", buf.getvalue(), "image/jpeg")})
        assert r.status_code == 200, r.text
        body = r.json()
        zmap = np.round(np.asarray(Image.open(io.BytesIO(base64.b64decode(body["map"].split(",")[1])))) / body["step"]).astype(np.uint8)
        assert zmap.shape == (body["height"], body["width"])
        pct = {z["zone"]: z["pct"] for z in body["zones"]}
        assert abs(sum(pct.values()) - 100) < 0.5
        for zones in (["suelo"], ["pared", "mobiliario"]):
            mask = np.isin(zmap, [seg.ZONE_ORDER.index(z) for z in zones])
            if mask.mean() < 0.02:
                continue
            mbuf = io.BytesIO()
            Image.fromarray((mask * 255).astype(np.uint8), "L").save(mbuf, format="PNG")
            r = api.post("/api/renovate", files={"image": ("f.jpg", buf.getvalue(), "image/jpeg"),
                                                 "mask": ("m.png", mbuf.getvalue(), "image/png")},
                         data={"style": "estilo nórdico", "zones": ",".join(zones)})
            assert r.status_code == 200, r.text
            out = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"), dtype=int)
            orig = np.asarray(service.preprocess(buf.getvalue(), 1024), dtype=int)
            far = ~(np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(33))) > 127)
            # Fuga = píxel lejos de la máscara que se ha vuelto verde (el color del
            # generador de prueba) sin serlo en la foto original. El ruido de la
            # compresión JPEG se mide aparte y es solo informativo.
            def greenish(a):
                return (a[..., 1] - np.maximum(a[..., 0], a[..., 2])) > 80
            leaked = float((greenish(out) & ~greenish(orig))[far].mean())
            jpeg_noise = float((np.abs(out - orig).max(axis=2)[far] > 12).mean())
            changed_in = float((np.abs(out - [0, 255, 0]).max(axis=2)[mask] <= 12).mean())
            ok = leaked == 0
            failures += not ok
            report.append(f"| {s['n']:02d} {s['query']} | " + ", ".join(f"{k} {v}" for k, v in pct.items() if v >= 1)
                          + f" | {'+'.join(zones)} | {100 * leaked:.3f}% {'✅' if ok else '❌'} | {100 * jpeg_noise:.3f}% | {100 * changed_in:.0f}% |")
            overlay = Image.blend(Image.fromarray(orig.astype(np.uint8)), Image.fromarray(palette[zmap]), 0.5)
            panels = [Image.fromarray(orig.astype(np.uint8)), overlay, Image.fromarray(out.astype(np.uint8))]
            for p in panels:
                p.thumbnail((512, 512))
            canvas = Image.new("RGB", (sum(p.width for p in panels), panels[0].height), "white")
            x = 0
            for p in panels:
                canvas.paste(p, (x, 0))
                x += p.width
            canvas.save(OUT / f"{s['n']:02d}-{'-'.join(zones).replace('/', '')}.jpg", quality=85)
    report += ["", "Verde = zona sustituida por el generador de prueba. Fuera de la máscara no debe haber verde."]
    (OUT / "report.md").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
