"""Informe: metadatos reales de cada candidata (Hugging Face y GitHub) + resultados
de las pruebas con fotos reales. Salida: results_3d/report.md."""

import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from r3d.common import INPUT, OUT  # noqa: E402

CANDIDATES = [
    # (nombre, entrada, modelo HF, repo GitHub, carpeta de resultados o None)
    ("Depth Anything V2 Small", "1 foto", "depth-anything/Depth-Anything-V2-Small-hf", "DepthAnything/Depth-Anything-V2", "depth_anything_v2_small"),
    ("MoGe-2 (ViT-L)", "1 foto", "Ruicheng/moge-2-vitl-normal", "microsoft/MoGe", "moge2"),
    ("Depth Pro (Apple)", "1 foto", "apple/DepthPro", "apple/ml-depth-pro", None),
    ("InSpace (panorámica 360°)", "1 panorámica", "GwanHyeong/InSpace", None, None),
    ("MapAnything (Apache)", "varias fotos", "facebook/map-anything-apache", "facebookresearch/map-anything", "mapanything_apache"),
    ("VGGT-1B-Commercial", "varias fotos", "facebook/VGGT-1B-Commercial", "facebookresearch/vggt", "vggt_1b_commercial"),
    ("MASt3R", "varias fotos", "naver/MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric", "naver/mast3r", None),
    ("SpatialLM 1.1", "nube → planta", "manycore-research/SpatialLM1.1-Qwen-0.5B", "manycore-research/SpatialLM", None),
    ("gsplat (entrenar Gaussian Splat)", "vídeo/fotos", None, "nerfstudio-project/gsplat", None),
    ("OpenSplat", "vídeo/fotos", None, "pierotofy/OpenSplat", None),
    ("SuperSplat (visor/editor web)", "visor", None, "playcanvas/supersplat", None),
]


def hf_meta(model_id):
    if not model_id:
        return {}
    from huggingface_hub import HfApi

    try:
        info = HfApi(token=os.environ.get("HF_TOKEN") or None).model_info(model_id, expand=["cardData", "downloads", "likes", "lastModified", "gated"])
        card = info.card_data.to_dict() if info.card_data else {}
        return {"license": card.get("license") or card.get("license_name") or "?", "downloads": info.downloads,
                "likes": info.likes, "updated": str(info.last_modified)[:10] if info.last_modified else "?", "gated": info.gated}
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__}


def gh_meta(repo):
    if not repo:
        return {}
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}", timeout=30,
                         headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"} if os.environ.get("GITHUB_TOKEN") else {}).json()
        return {"stars": r.get("stargazers_count"), "pushed": (r.get("pushed_at") or "?")[:10],
                "code_license": (r.get("license") or {}).get("spdx_id", "?")}
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__}


def main():
    lines = ["# Reconstrucción 3D de habitaciones: candidatas y pruebas", "",
             "Metadatos consultados en vivo (Hugging Face y GitHub) en esta ejecución. "
             "Pruebas en la CPU de un runner de GitHub Actions (4 núcleos, sin GPU).", "",
             "## Candidatas", "", "| Herramienta | Entrada | Licencia pesos (ficha HF) | Acceso | Licencia código | ★ GitHub | Última actividad | Descargas HF |",
             "|---|---|---|---|---|---|---|---|"]
    for name, inp, mid, repo, _ in CANDIDATES:
        h, g = hf_meta(mid), gh_meta(repo)
        lines.append(f"| {name} | {inp} | {h.get('license', '—') if mid else '—'} | {('restringido' if h.get('gated') else 'libre') if mid and 'error' not in h else ('—' if not mid else h.get('error'))} | "
                     f"{g.get('code_license', '—')} | {g.get('stars', '—')} | {max(filter(None, [h.get('updated'), g.get('pushed')]), default='—')} | {h.get('downloads', '—')} |")
    lines += ["", "## Pruebas con fotos reales", "", "| Método | Caso | Resultado | Tiempo CPU | Puntos | Notas |", "|---|---|---|---|---|---|"]
    renders = []
    for _, _, _, _, folder in CANDIDATES:
        if not folder or not (OUT / folder).is_dir():
            continue
        for j in sorted((OUT / folder).glob("*.json")):
            r = json.loads(j.read_text(encoding="utf-8"))
            notes = {k: v for k, v in r.items() if k not in ("method", "case", "ok", "seconds", "points", "error", "model")}
            lines.append(f"| {r['method']} | {r['case']} | {'✅' if r['ok'] else '❌ ' + r.get('error', '')[:160]} | {r['seconds']} s | {r.get('points', '—')} | {notes or ''} |")
            if r["ok"]:
                renders.append(f"### {r['method']} — {r['case']}\n\n![]({folder}/{r['case']}.jpg)\n\nNube: `{folder}/{r['case']}.glb`\n")
    lines += ["", "## Vistas (original, girada 30°, desde arriba)", "", *renders, "## Fotos de entrada", ""]
    credits = json.loads((INPUT / "credits.json").read_text(encoding="utf-8")) if (INPUT / "credits.json").exists() else []
    lines += [f"- [{c['title']}]({c['source']}) — {c['artist']}, {c['license']}" for c in credits]
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
