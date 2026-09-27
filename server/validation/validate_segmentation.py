"""Valida la segmentación de interiores ANTES de conectarla a la interfaz.

Descarga fotos de interiores con licencia libre de Wikimedia Commons (más las
que haya en server/validation/fotos/), las segmenta con SegFormer entrenado en
ADE20K, agrupa las clases en las zonas que usará HomeAI y genera:

  results/<n>.jpg   foto original | zonas coloreadas
  results/report.md tabla por foto: % de cada zona, confianza media y aviso
                    de posibles fallos, más la atribución de cada foto.

Se ejecuta en GitHub Actions (.github/workflows/validate-segmentation.yml),
porque el entorno de desarrollo no llega a huggingface.co. No necesita token:
el modelo es público y corre en la CPU del runner.
"""

from __future__ import annotations

import html
import io
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

MODEL_ID = "nvidia/segformer-b0-finetuned-ade-512-512"
HERE = Path(__file__).parent
OUT = HERE / "results"
LOCAL = HERE / "fotos"
UA = {"User-Agent": "HomeAI-segmentation-validation/1.0 (https://github.com/JuanCopado/homeai-claude)"}

# Clases de ADE20K (nombres del id2label del modelo) agrupadas en zonas.
ZONES = {
    "pared": {"wall"},
    "suelo": {"floor"},
    "techo": {"ceiling"},
    "ventana/puerta": {"windowpane", "window", "door", "screen door", "double door"},
    "mobiliario": {
        "bed", "cabinet", "table", "chair", "sofa", "shelf", "armchair", "seat", "desk",
        "wardrobe", "lamp", "bathtub", "cushion", "chest of drawers", "counter", "sink",
        "fireplace", "refrigerator", "pillow", "bookcase", "coffee table", "toilet",
        "countertop", "stove", "kitchen island", "swivel chair", "chandelier", "ottoman",
        "buffet", "stool", "oven", "microwave", "dishwasher", "shower", "radiator",
        "television receiver", "curtain", "blind", "rug", "painting", "mirror", "plant",
        "bench", "cradle", "sconce", "hood", "washer", "towel", "vase", "clock", "light",
    },
}
COLORS = {
    "pared": (231, 111, 81), "suelo": (42, 157, 143), "techo": (233, 196, 106),
    "ventana/puerta": (69, 123, 157), "mobiliario": (155, 93, 229), "otros": (120, 120, 120),
}
ZONE_ORDER = list(ZONES) + ["otros"]

QUERIES = [
    "filetype:bitmap living room interior",
    "filetype:bitmap kitchen interior",
    "filetype:bitmap bedroom interior",
    "filetype:bitmap bathroom interior",
    "filetype:bitmap attic room interior sloped ceiling",
    "filetype:bitmap dark room interior",
]
PER_QUERY = 2
ALLOWED_LICENSES = re.compile(r"^(CC0|Public domain|CC BY(-SA)? [0-9.]+)", re.I)


def norm(label: str) -> str:
    return label.strip().lower().split(",")[0].strip()


def zone_of(label: str) -> str:
    n = norm(label)
    for zone, names in ZONES.items():
        if n in names:
            return zone
    return "otros"


def fetch_commons(max_total: int = 10) -> list[dict]:
    import requests

    picked, seen = [], set()
    for q in QUERIES:
        params = {
            "action": "query", "format": "json", "generator": "search", "gsrsearch": q,
            "gsrnamespace": 6, "gsrlimit": 25, "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1280,
        }
        try:
            data = requests.get("https://commons.wikimedia.org/w/api.php", params=params, headers=UA, timeout=30).json()
        except Exception as exc:  # noqa: BLE001
            print(f"[aviso] búsqueda '{q}' falló: {exc}")
            continue
        n = 0
        pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
        for page in pages:
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata", {})
            lic = meta.get("LicenseShortName", {}).get("value", "")
            if info.get("mime") not in ("image/jpeg", "image/png") or info.get("width", 0) < 800:
                continue
            if not ALLOWED_LICENSES.match(lic) or page["title"] in seen:
                continue
            artist = re.sub(r"<[^>]+>", "", html.unescape(meta.get("Artist", {}).get("value", "desconocido"))).strip()
            try:
                raw = requests.get(info.get("thumburl") or info["url"], headers=UA, timeout=60).content
                img = Image.open(io.BytesIO(raw))
                img.load()
            except Exception as exc:  # noqa: BLE001
                print(f"[aviso] no se pudo descargar {page['title']}: {exc}")
                continue
            seen.add(page["title"])
            picked.append({"image": img, "source": info.get("descriptionurl", ""), "title": page["title"],
                           "license": lic, "artist": artist[:80], "query": q.replace("filetype:bitmap ", "")})
            n += 1
            if n >= PER_QUERY or len(picked) >= max_total:
                break
        if len(picked) >= max_total:
            break
    return picked


def load_local() -> list[dict]:
    out = []
    if LOCAL.is_dir():
        for p in sorted(LOCAL.iterdir()):
            if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                out.append({"image": Image.open(p), "source": str(p.relative_to(HERE)), "title": p.name,
                            "license": "local", "artist": "-", "query": "foto local"})
    return out


class Segmenter:
    def __init__(self):
        import torch
        from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor

        self.torch = torch
        self.proc = SegformerImageProcessor.from_pretrained(MODEL_ID)
        self.model = SegformerForSemanticSegmentation.from_pretrained(MODEL_ID).eval()
        self.id2label = self.model.config.id2label

    def __call__(self, img: Image.Image) -> tuple[np.ndarray, np.ndarray]:
        """Devuelve (mapa de clases, confianza por píxel) al tamaño de la foto."""
        torch = self.torch
        with torch.no_grad():
            logits = self.model(**self.proc(images=img, return_tensors="pt")).logits
            logits = torch.nn.functional.interpolate(logits, size=img.size[::-1], mode="bilinear", align_corners=False)
            probs = logits.softmax(dim=1)[0]
            conf, labels = probs.max(dim=0)
        return labels.numpy(), conf.numpy()


def zone_map(labels: np.ndarray, id2label: dict) -> np.ndarray:
    lut = np.array([ZONE_ORDER.index(zone_of(id2label[i])) for i in range(len(id2label))], dtype=np.uint8)
    return lut[labels]


def analyse(zmap: np.ndarray, conf: np.ndarray, labels: np.ndarray, id2label: dict) -> dict:
    total = zmap.size
    stats = {}
    for zi, zone in enumerate(ZONE_ORDER):
        m = zmap == zi
        share = m.sum() / total
        stats[zone] = {"pct": round(100 * share, 1), "conf": round(float(conf[m].mean()), 2) if m.any() else None}
    ids, counts = np.unique(labels, return_counts=True)
    top = sorted(zip(counts, ids), reverse=True)[:6]
    stats["_top"] = [f"{norm(id2label[int(i)])} {100 * c / total:.0f}%" for c, i in top]
    warn = []
    if stats["pared"]["pct"] < 10:
        warn.append("apenas detecta pared")
    if stats["suelo"]["pct"] < 3:
        warn.append("apenas detecta suelo")
    if stats["otros"]["pct"] > 25:
        warn.append(f"{stats['otros']['pct']}% en clases fuera de las zonas")
    low = [z for z in ZONES if stats[z]["conf"] is not None and stats[z]["pct"] > 3 and stats[z]["conf"] < 0.6]
    if low:
        warn.append("confianza baja en " + ", ".join(low))
    stats["_warn"] = warn
    return stats


def render(img: Image.Image, zmap: np.ndarray, stats: dict, path: Path) -> None:
    palette = np.array([COLORS[z] for z in ZONE_ORDER], dtype=np.uint8)
    color = Image.fromarray(palette[zmap])
    overlay = Image.blend(img, color, 0.55)
    w, h = img.size
    canvas = Image.new("RGB", (w * 2, h + 40), "white")
    canvas.paste(img, (0, 0))
    canvas.paste(overlay, (w, 0))
    d = ImageDraw.Draw(canvas)
    x = 8
    for z in ZONE_ORDER:
        d.rectangle((x, h + 12, x + 16, h + 28), fill=COLORS[z])
        label = f"{z} {stats[z]['pct']}%"
        d.text((x + 22, h + 14), label, fill=(20, 20, 20))
        x += 30 + 7 * len(label)
    canvas.save(path, quality=85)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    photos = load_local() + fetch_commons()
    if not photos:
        print("No hay fotos: ni en fotos/ ni descargadas de Wikimedia Commons.")
        return 1
    seg = Segmenter()
    rows, summary = [], []
    for n, ph in enumerate(photos, 1):
        img = ImageOps.exif_transpose(ph["image"]).convert("RGB")
        if max(img.size) > 1024:
            img.thumbnail((1024, 1024))
        labels, conf = seg(img)
        zmap = zone_map(labels, seg.id2label)
        stats = analyse(zmap, conf, labels, seg.id2label)
        name = f"{n:02d}.jpg"
        render(img, zmap, stats, OUT / name)
        summary.append({"n": n, "title": ph["title"], "query": ph["query"], **{z: stats[z] for z in ZONE_ORDER},
                        "top": stats["_top"], "warn": stats["_warn"]})
        cells = " | ".join(f"{stats[z]['pct']}% ({stats[z]['conf'] if stats[z]['conf'] is not None else '-'})" for z in ZONE_ORDER)
        rows.append(f"| {n} | {ph['query']} | {cells} | {'; '.join(stats['_warn']) or 'ok'} |")
        pcts = ' '.join(f"{z}={stats[z]['pct']}%" for z in ZONE_ORDER)
        print(f"{n:02d} {ph['title'][:50]:50} {pcts}  {stats['_warn'] or 'ok'}")

    report = [
        "# Validación de la segmentación por zonas",
        "",
        f"Modelo: `{MODEL_ID}` (ADE20K, CPU). Cada imagen: original a la izquierda, zonas a la derecha.",
        "Formato de celda: % de la foto (confianza media del modelo en esa zona, 0–1).",
        "",
        "| # | Tipo | " + " | ".join(ZONE_ORDER) + " | Avisos |",
        "|---|---|" + "---|" * len(ZONE_ORDER) + "---|",
        *rows,
        "",
        *[f"## {s['n']:02d} — {s['query']}\n\n![{s['n']:02d}]({s['n']:02d}.jpg)\n\nClases principales: {', '.join(s['top'])}\n"
          for s in summary],
        "## Atribución de las fotos",
        "",
        *[f"- {n:02d}: [{ph['title']}]({ph['source']}) — {ph['artist']}, {ph['license']}" for n, ph in enumerate(photos, 1)],
        "",
    ]
    (OUT / "report.md").write_text("\n".join(report), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(photos)} fotos procesadas. Informe: {OUT / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
