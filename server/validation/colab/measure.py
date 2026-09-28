"""Medición de QA del pipeline Qwen-Image-Edit en Google Colab (GPU gratuita).

Ejecuta el MISMO código que producción (pipeline.py: instrucción, filtro de
similitud antes del puntuador, regeneración de las casi idénticas,
puntuador, elección) pero con el modelo en la GPU de Colab vía diffusers
(local_qwen.py) en lugar de la Inference API de pago.

En una T4 (16 GB) no caben a la vez el codificador (Qwen2.5-VL 7B) y el
transformer (20B), ni en 4 bits, así que va por fases:

1. Codificar todas las instrucciones (+ foto) con Qwen2.5-VL en 4 bits.
2. Liberar la GPU; cargar el transformer en 4 bits (+ LoRA Lightning, 8
   pasos) y generar 2 variantes por foto; filtro de similitud; regenerar
   una vez las casi idénticas.
3. Puntuar (CPU) solo las que pasan el filtro.
4. Opcional: SDXL img2img sobre las mismas fotos, como referencia de calidad
   (SDXL ya no se sirve por la API; aquí corre en la propia GPU).

Salida en out_dir: report.md, data.json y una rejilla por foto
(original | SDXL | variantes Qwen con su similitud y nota).
"""

from __future__ import annotations

import gc
import io
import json
import re
import time
import traceback
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import pipeline

UA = "HomeAI-QA/1.0 (https://github.com/JuanCopado/homeai-claude)"
# Las 10 fotos reales de la validación de segmentación (Wikimedia Commons,
# licencias libres; la atribución se escribe en el informe).
PHOTOS = [
    "File:Living room in apartment of Condomínio do Edifício Zaher, Le Blond, Rio de Janeiro, Brazil.jpg",
    "File:Apartment Living Room 4 2018-09-28.jpg",
    "File:Empty apartment living room.jpg",
    "File:A Dingy Apartment Kitchen in Canada.jpg",
    "File:Empty apartment in Berlin with fitted kitchen and chair.jpg",
    "File:Apartment Kitchen 1 2018-09-28.jpg",
    "File:Bedroom in a serviced apartment in London.jpg",
    "File:Bedroom, Interior of apartment in Brisbane, 2025, 02.jpg",
    "File:Bedroom, Interior of apartment in Brisbane, 2025, 01.jpg",
    "File:02023 0113 Bathroom, Presidential private apartment in Wawel Castle.jpg",
]
STYLES = [
    "estilo nórdico escandinavo, paredes blancas, madera clara, textiles de lino, plantas",
    "estilo industrial, ladrillo visto, metal negro, madera oscura",
    "estilo japandi, tonos tierra, madera natural, líneas simples",
    "estilo mediterráneo, blanco y azul, cerámica, fibras naturales",
    "estilo moderno minimalista, gris claro, muebles lacados, iluminación indirecta",
]
# Intensidad por foto: la mayoría la de la interfaz (0,55); tres "retoque"
# (0,3), donde es más probable que el modelo casi no cambie nada y el filtro
# de similitud tenga trabajo, y dos "rediseño completo" (0,75).
STRENGTHS = [0.55, 0.3, 0.55, 0.75, 0.3, 0.55, 0.55, 0.3, 0.75, 0.55]


def default_jobs():
    return [{"n": i + 1, "title": t, "style": STYLES[i % len(STYLES)], "strength": STRENGTHS[i]}
            for i, t in enumerate(PHOTOS)]


def fetch_photo(title: str, width: int = 1024):
    import requests

    r = requests.get("https://commons.wikimedia.org/w/api.php", headers={"User-Agent": UA}, timeout=60, params={
        "action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url|extmetadata",
        "iiurlwidth": width, "format": "json"})
    info = next(iter(r.json()["query"]["pages"].values()))["imageinfo"][0]
    meta = info.get("extmetadata", {})
    artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "?")).strip()
    credit = f"[{title}]({info['descriptionurl']}) — {artist}, {meta.get('LicenseShortName', {}).get('value', '?')}"
    img = Image.open(io.BytesIO(requests.get(info["thumburl"], headers={"User-Agent": UA}, timeout=120).content))
    return img.convert("RGB"), credit


def prepare(img: Image.Image, max_side: int = 1024) -> Image.Image:
    """Como app.preprocess: lado mayor ≤ 1024 y múltiplo de 8."""
    s = min(1.0, max_side / max(img.size))
    w, h = max(8, int(img.width * s) // 8 * 8), max(8, int(img.height * s) // 8 * 8)
    return img.resize((w, h), Image.LANCZOS)


def broken(img: Image.Image) -> str | None:
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    if not np.isfinite(a).all():
        return "nan"
    if a.max() < 8 or a.std() < 1.0:
        return "negra_o_plana"  # síntoma típico de desbordamiento en fp16
    return None


def _free():
    gc.collect()
    try:
        import torch

        torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass


def drop_cache(repo: str, folder: str) -> float:
    """Borra de la caché de HF una subcarpeta ya usada (p. ej. el codificador
    tras la fase 1) para que el disco de Colab (~80 GB libres) no se llene:
    codificador 15,4 GB + transformer 38,1 GB + SDXL 7 GB no caben a la vez
    con holgura. Devuelve los GB liberados."""
    try:
        from huggingface_hub import scan_cache_dir
    except Exception:  # noqa: BLE001
        return 0.0
    freed = 0
    for r in scan_cache_dir().repos:
        if r.repo_id != repo:
            continue
        for rev in r.revisions:
            for f in rev.files:
                if f.file_name and f"/{folder}/" in str(f.file_path).replace("\\", "/"):
                    for p in (f.blob_path, f.file_path):
                        try:
                            freed += p.stat().st_size if p == f.blob_path else 0
                            p.unlink()
                        except OSError:
                            pass
    return round(freed / 2**30, 1)


def _vram():
    try:
        import torch

        return round(torch.cuda.max_memory_allocated() / 2**30, 1) if torch.cuda.is_available() else None
    except Exception:  # noqa: BLE001
        return None


def run(out_dir: str | Path = "qa_qwen", jobs=None, variants: int = 2, lightning: bool = True, quant: str = "nf4",
        max_similarity: float = 0.89, min_score: float = 0.5, sdxl: bool = True, steps: int | None = None,
        loaders: dict | None = None, fetch=fetch_photo, log=print, free_disk: bool = True) -> dict:
    """loaders: {"text": f(), "image": f(), "sdxl": f()} para sustituir la carga
    real (el smoke test de CI usa un modelo diminuto en CPU)."""
    import local_qwen

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    jobs = jobs or default_jobs()
    loaders = loaders or {}
    true_cfg = 1.0 if lightning else 4.0
    steps = steps or (8 if lightning else 30)
    data = {"config": {"variants": variants, "lightning": lightning, "quant": quant, "steps": steps, "true_cfg": true_cfg,
                       "max_similarity": max_similarity, "min_score": min_score}, "jobs": [], "errors": []}

    # 0. Fotos
    for j in jobs:
        img, credit = fetch(j["title"])
        j["image"], j["credit"] = prepare(img), credit
        j["prompt"] = pipeline.build_prompt(j["style"], [], j["strength"], edit=True)
        log(f"foto {j['n']:02d} {j['image'].size}")

    # Si algo falla a mitad (memoria, desconexión del modelo...), se escribe
    # igualmente el informe con lo que se haya medido hasta ese momento.
    try:
        # 1. Codificar (Qwen2.5-VL)
        t0 = time.perf_counter()
        text = loaders.get("text", lambda: local_qwen.load(parts="text", quant=quant, lightning=False))()
        for j in jobs:
            j["emb"] = local_qwen.encode(text, j["image"], j["prompt"], pipeline.DEFAULT_NEGATIVE)
        data["encode_seconds"] = round(time.perf_counter() - t0, 1)
        data["vram_text_gb"] = _vram()
        del text
        _free()
        log(f"codificado en {data['encode_seconds']} s")
        if free_disk:
            log(f"caché del codificador borrada: {drop_cache(local_qwen.MODEL, 'text_encoder')} GB")

        # 2. Generar + filtro de similitud + regenerar las casi idénticas
        t0 = time.perf_counter()
        try:
            editor = loaders.get("image", lambda: local_qwen.load(parts="image", quant=quant, lightning=lightning))()
        except Exception as exc:  # noqa: BLE001 - sin LoRA se puede seguir, más lento
            if not lightning:
                raise
            data["errors"].append(f"LoRA Lightning no cargó ({type(exc).__name__}: {exc}); se sigue sin ella")
            lightning, true_cfg, steps = False, 4.0, 30
            data["config"].update(lightning=False, true_cfg=true_cfg, steps=steps)
            _free()
            editor = local_qwen.load(parts="image", quant=quant, lightning=False)
        data["load_image_seconds"] = round(time.perf_counter() - t0, 1)
        seed = 1000

        def gen(j):
            nonlocal seed
            seed += 1
            t = time.perf_counter()
            try:
                img = local_qwen.render(editor, j["image"], j["emb"], steps, true_cfg, seed)
            except Exception as exc:  # noqa: BLE001
                data["errors"].append(f"foto {j['n']:02d}: {type(exc).__name__}: {exc}")
                log(traceback.format_exc())
                _free()
                return None
            img = img.convert("RGB").resize(j["image"].size, Image.LANCZOS)
            v = {"image": img, "seconds": round(time.perf_counter() - t, 1), "seed": seed, "broken": broken(img)}
            log(f"  foto {j['n']:02d} semilla {seed}: {v['seconds']} s" + (f" ⚠️ {v['broken']}" if v["broken"] else ""))
            return v

        for j in jobs:
            vs = [v for v in (gen(j) for _ in range(variants)) if v]
            pipeline.check_similarity(vs, j["image"], None, max_similarity)
            same = [v for v in vs if v.get("reason") == "sin_cambios"]
            more = [v for v in (gen(j) for _ in same) if v]
            pipeline.check_similarity(more, j["image"], None, max_similarity)
            for v in more:
                v["regenerated"] = True
            j["variants"] = vs + more
        data["generate_seconds"] = round(time.perf_counter() - t0, 1)
        data["vram_image_gb"] = _vram()
        editor = None  # noqa: F841 - libera la GPU antes de SDXL
        _free()
        if free_disk and sdxl:
            log(f"caché del transformer borrada: {drop_cache(local_qwen.MODEL, 'transformer')} GB")

        # 3. Puntuador, solo sobre las que pasaron el filtro
        for j in jobs:
            pipeline.score_variants(j["variants"], min_score)
            if j["variants"]:
                j["best"] = pipeline.pick_best(j["variants"])

        # 4. Referencia SDXL (misma foto, prompt y strength del pipeline antiguo)
        if sdxl:
            try:
                ref = loaders.get("sdxl", _load_sdxl)()
                import quality

                for j in jobs:
                    t = time.perf_counter()
                    img = ref(prompt=pipeline.build_prompt(j["style"], [], edit=False), negative_prompt=pipeline.DEFAULT_NEGATIVE,
                              image=j["image"], strength=j["strength"], num_inference_steps=30, guidance_scale=7.0).images[0]
                    img = img.convert("RGB").resize(j["image"].size, Image.LANCZOS)
                    j["sdxl"] = {"image": img, "seconds": round(time.perf_counter() - t, 1),
                                 "similarity": quality.similarity(img, j["image"]), **quality.score(img)}
                del ref
                _free()
            except Exception as exc:  # noqa: BLE001
                data["errors"].append(f"SDXL: {type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001
        data["errors"].append(f"Parada: {type(exc).__name__}: {exc}")
        log(traceback.format_exc())

    _write(out, jobs, data)
    data["jobs"] = jobs
    return data


def _load_sdxl():
    import torch
    from diffusers import StableDiffusionXLImg2ImgPipeline

    return StableDiffusionXLImg2ImgPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16, variant="fp16").to("cuda")


def _tile(img, label, h=300):
    t = img.copy()
    t.thumbnail((h * 2, h))
    d = ImageDraw.Draw(t)
    d.rectangle((0, 0, 8 + 6 * len(label), 16), fill=(255, 255, 255))
    d.text((4, 2), label, fill=(0, 0, 0))
    return t


def _write(out: Path, jobs, data):
    gens = [v for j in jobs for v in j.get("variants", [])]
    first = [v for v in gens if not v.get("regenerated")]
    regen = [v for v in gens if v.get("regenerated")]
    near = [v for v in first if v.get("reason") == "sin_cambios"]
    secs = [v["seconds"] for v in gens]
    lines = ["# Qwen-Image-Edit en Colab: medición del pipeline", "",
             f"Configuración: `{json.dumps(data['config'], ensure_ascii=False)}`", "",
             "## Estabilidad", "",
             f"- Generaciones completadas: **{len(gens)}** (primeras {len(first)} + regeneradas {len(regen)}); "
             f"errores: **{len(data['errors'])}**.",
             f"- Imágenes negras/NaN: **{sum(1 for v in gens if v.get('broken'))}**.",
             (f"- Tiempo por generación: media {np.mean(secs):.1f} s, mín {min(secs):.1f}, máx {max(secs):.1f}."
              if secs else "- Sin tiempos."),
             f"- Codificación de todas las instrucciones: {data.get('encode_seconds')} s; carga del transformer: "
             f"{data.get('load_image_seconds')} s.",
             f"- VRAM máxima: codificador {data.get('vram_text_gb')} GB, transformer {data.get('vram_image_gb')} GB.", ""]
    if data["errors"]:
        lines += ["Errores:", "", *[f"- `{e}`" for e in data["errors"]], ""]
    lines += ["## Filtro de similitud (antes del puntuador)", "",
              f"- Umbral: similitud CLIP > {data['config']['max_similarity']} → casi idéntica.",
              f"- Descartadas en la primera tanda: **{len(near)}/{len(first)}**"
              + (f" ({100 * len(near) / len(first):.0f} %)." if first else "."),
              f"- Regeneradas: {len(regen)}; de ellas, otra vez casi idénticas: "
              f"{sum(1 for v in regen if v.get('reason') == 'sin_cambios')}.",
              "- Similitudes de todas las generaciones: "
              + ", ".join(str(v.get("similarity")) for v in gens), ""]
    lines += ["## Calidad", "",
              "| Foto | Intensidad | Estilo | SDXL (nota / similitud) | Qwen: nota / similitud por variante | Elegida |",
              "|---|---|---|---|---|---|"]
    for j in jobs:
        sd = j.get("sdxl")
        sd_txt = f"{sd['score']} / {sd['similarity']}" if sd else "—"
        vs = "; ".join(f"v{i + 1}{'ʳ' if v.get('regenerated') else ''} {v.get('score', '—')} / {v.get('similarity')}"
                       + (f" ({v['reason']})" if v.get("reason") else "") for i, v in enumerate(j.get("variants", [])))
        best = j.get("best")
        lines.append(f"| {j['n']:02d} | {j['strength']} | {j['style'].split(',')[0]} | {sd_txt} | {vs or '—'} | "
                     f"{'v' + str(best + 1) if best is not None else '—'} |")
        tiles = [_tile(j["image"], "original")]
        if sd:
            tiles.append(_tile(sd["image"], f"SDXL s={sd['score']} sim={sd['similarity']}"))
        for i, v in enumerate(j.get("variants", [])):
            mark = "*" if i == best else ""
            tiles.append(_tile(v["image"], f"Qwen v{i + 1}{mark} s={v.get('score', '-')} sim={v.get('similarity')}"
                               + (" DESCARTADA" if v.get("discarded") else "")))
        grid = Image.new("RGB", (sum(t.width for t in tiles), max(t.height for t in tiles)), "white")
        x = 0
        for t in tiles:
            grid.paste(t, (x, 0))
            x += t.width
        grid.save(out / f"{j['n']:02d}.jpg", quality=85)
    q = [v["score"] for v in gens if v.get("score") is not None]
    s = [j["sdxl"]["score"] for j in jobs if j.get("sdxl")]
    lines += ["", f"Nota media Qwen (las que pasaron el filtro): {np.mean(q):.3f}" if q else "",
              f"Nota media SDXL: {np.mean(s):.3f}" if s else "",
              "", "La comparación subjetiva se hace mirando las rejillas:", "",
              *[f"![{j['n']:02d}]({j['n']:02d}.jpg)" for j in jobs], "", "## Fotos", "",
              *[f"- {j['n']:02d}: {j.get('credit', j['title'])}" for j in jobs]]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    slim = {k: v for k, v in data.items() if k != "jobs"}
    slim["jobs"] = [{"n": j["n"], "title": j["title"], "style": j["style"], "strength": j["strength"],
                     "prompt": j["prompt"], "best": j.get("best"),
                     "sdxl": {k: v for k, v in j["sdxl"].items() if k != "image"} if j.get("sdxl") else None,
                     "variants": [{k: v for k, v in x.items() if k != "image"} for x in j.get("variants", [])]}
                    for j in jobs]
    (out / "data.json").write_text(json.dumps(slim, ensure_ascii=False, indent=1), encoding="utf-8")
