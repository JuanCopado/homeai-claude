"""Mide varias variantes por petición ANTES de implementar el filtro de calidad.

Con el token real (secreto HF_TOKEN de GitHub Actions) y el código de
producción (app.generate):

1. Qué modelos candidatos sirve hoy algún proveedor para image-to-image, y
   con cuál se mide (el primero disponible).
2. Latencia: 1 variante sola frente a 2 y 3 en paralelo (hilos).
3. Calidad: cada variante se puntúa con quality.py (LAION aesthetic + CLIP
   realismo) y se guarda una rejilla original | variantes (con su nota) para
   comprobar a ojo si el puntuador elige la buena y descarta la mala.

Fotos: 5 de la validación de segmentación, elegidas por ser casos difíciles
(contraluz, pasillo estrecho, ángulo raro, habitación vacía y oscura, baño
pequeño). Presupuesto: ~26 generaciones; si se agota el crédito (HTTP 402)
se para y el informe dice hasta dónde llegó.

Salida: results_variants/ (NN.jpg + report.md + data.json).
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

from PIL import Image, ImageDraw  # noqa: E402

OUT = HERE / "results_variants"
CANDIDATES = [
    "stabilityai/stable-diffusion-xl-base-1.0",
    "black-forest-labs/FLUX.1-Kontext-dev",
    "Qwen/Qwen-Image-Edit",
    "timbrooks/instruct-pix2pix",
    "stabilityai/stable-diffusion-xl-refiner-1.0",
]
PHOTOS = {  # n de validation/results/summary.json -> motivo
    1: "contraluz (ventanales al atardecer)",
    4: "pasillo-cocina estrecho",
    6: "cocina con ángulo abierto",
    3: "habitación vacía y oscura",
    10: "baño pequeño con espejo",
}
STYLE = "estilo nórdico escandinavo, paredes blancas, madera clara, textiles de lino, plantas"
PARALLEL2_ON = {1, 4}


def model_availability(token: str) -> list[tuple[str, list[str]]]:
    from huggingface_hub import HfApi

    api, out = HfApi(token=token), []
    for m in CANDIDATES:
        try:
            info = api.model_info(m, expand=["inferenceProviderMapping"])
            provs = [f"{x.provider} ({x.status})" for x in (info.inference_provider_mapping or [])
                     if getattr(x, "task", None) == "image-to-image"]
        except Exception as exc:  # noqa: BLE001
            provs = [f"error: {type(exc).__name__}"]
        out.append((m, provs))
    return out


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for old in OUT.iterdir():
        old.unlink()
    token = os.environ.get("HF_TOKEN", "").strip()
    report = ["# Variantes por petición: medición con el modelo real", ""]
    if not token:
        report.append("**No se ejecutó: falta el secreto `HF_TOKEN` en GitHub** "
                      "(Settings → Secrets and variables → Actions → New repository secret).")
        (OUT / "report.md").write_text("\n".join(report), encoding="utf-8")
        print(report[-1])
        return 0

    avail = model_availability(token)
    report += ["## Modelos candidatos servidos para image-to-image", "", "| Modelo | Proveedores |", "|---|---|",
               *[f"| `{m}` | {', '.join(p) or '— ninguno'} |" for m, p in avail], ""]
    live = [m for m, p in avail if any("live" in x for x in p)] or [m for m, p in avail if p and not p[0].startswith("error")]
    if not live:
        report.append("**Ningún candidato está servido para image-to-image: no se puede medir con este token.**")
        (OUT / "report.md").write_text("\n".join(report), encoding="utf-8")
        print("\n".join(report))
        return 1
    os.environ["HF_MODEL"] = live[0]
    os.environ.setdefault("HF_PROVIDER", "auto")

    import app as service
    import quality
    from compare_models import fetch_by_title

    cfg = service.settings()
    prompt = service.build_prompt(STYLE, [])
    summary = {s["n"]: s for s in json.loads((HERE / "results" / "summary.json").read_text(encoding="utf-8"))}
    report += [f"Modelo usado: `{live[0]}` (proveedor `{cfg['provider']}`), strength 0,55, {cfg['steps']} pasos.", ""]
    data, calls, stopped = [], 0, None

    def gen(img):
        nonlocal calls
        calls += 1
        t0 = time.perf_counter()
        out = service.generate(img, prompt, 0.55, cfg)
        return out, time.perf_counter() - t0

    for n, why in PHOTOS.items():
        if stopped:
            break
        src = fetch_by_title(summary[n]["title"]).convert("RGB")
        buf = io.BytesIO()
        src.save(buf, format="JPEG", quality=92)
        img = service.preprocess(buf.getvalue(), cfg["max_side"])
        row = {"n": n, "why": why, "title": summary[n]["title"], "variants": [], "latency": {}}
        try:
            one, t1 = gen(img)
            row["latency"]["1"] = round(t1, 1)
            row["variants"].append(one)
            if n in PARALLEL2_ON:
                t0 = time.perf_counter()
                with ThreadPoolExecutor(2) as ex:
                    two = [f.result()[0] for f in [ex.submit(gen, img) for _ in range(2)]]
                row["latency"]["2∥"] = round(time.perf_counter() - t0, 1)
                row["variants"] += two
            t0 = time.perf_counter()
            with ThreadPoolExecutor(3) as ex:
                three = [f.result()[0] for f in [ex.submit(gen, img) for _ in range(3)]]
            row["latency"]["3∥"] = round(time.perf_counter() - t0, 1)
            row["variants"] += three
        except service.ApiError as exc:
            row["error"] = f"{exc.code}: {exc.message}"
            if exc.code in ("quota_exhausted", "not_configured", "model_unsupported"):
                stopped = exc.code
        row["orig_score"] = quality.score(img)
        row["scores"] = [quality.score(v) for v in row["variants"]]
        data.append(row)
        # Rejilla: original + variantes con su nota; la mejor, marcada.
        tiles = [img] + row["variants"]
        best = max(range(len(row["scores"])), key=lambda i: row["scores"][i]["score"]) if row["scores"] else None
        thumbs = []
        for i, t in enumerate(tiles):
            t = t.copy()
            t.thumbnail((360, 360))
            d = ImageDraw.Draw(t)
            if i == 0:
                label = f"original  s={row['orig_score']['score']}"
            else:
                sc = row["scores"][i - 1]
                label = f"v{i}  s={sc['score']} (est {sc['aesthetic']}, real {sc['realism']})" + ("  ★" if i - 1 == best else "")
            d.rectangle((0, 0, 8 + 6 * len(label), 16), fill=(255, 255, 255))
            d.text((4, 2), label, fill=(0, 0, 0))
            thumbs.append(t)
        grid = Image.new("RGB", (sum(t.width for t in thumbs), max(t.height for t in thumbs)), "white")
        x = 0
        for t in thumbs:
            grid.paste(t, (x, 0))
            x += t.width
        grid.save(OUT / f"{n:02d}.jpg", quality=85)

    report += ["## Latencia (segundos por petición completa)", "", "| Foto | Caso | 1 variante | 2 en paralelo | 3 en paralelo |",
               "|---|---|---|---|---|"]
    for r in data:
        lat = r["latency"]
        report.append(f"| {r['n']:02d} | {r['why']} | {lat.get('1', '—')} | {lat.get('2∥', '—')} | {lat.get('3∥', '—')} |"
                      + (f" ⚠️ {r['error']}" if r.get("error") else ""))
    report += ["", "## Puntuaciones", "", "| Foto | Original | Variantes (score) | Mejor − peor |", "|---|---|---|---|"]
    for r in data:
        s = [v["score"] for v in r["scores"]]
        spread = round(max(s) - min(s), 3) if s else "—"
        report.append(f"| {r['n']:02d} | {r['orig_score']['score']} | {', '.join(map(str, s)) or '—'} | {spread} |")
    report += ["", f"Generaciones hechas: {calls}." + (f" Parada: `{stopped}`." if stopped else ""), "",
               *[f"![{r['n']:02d}]({r['n']:02d}.jpg)" for r in data], "",
               "Fotos: Wikimedia Commons, atribución en `../results/report.md`."]
    (OUT / "report.md").write_text("\n".join(report), encoding="utf-8")
    (OUT / "data.json").write_text(json.dumps([{k: v for k, v in r.items() if k != "variants"} for r in data],
                                              ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
