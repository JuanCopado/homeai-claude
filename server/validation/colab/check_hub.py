"""Comprueba en el Hub de Hugging Face lo que el notebook da por hecho, sin
descargar pesos ni gastar crédito (solo metadatos):

- Tamaño real de cada parte de Qwen/Qwen-Image-Edit (¿cabe en el disco y la
  RAM de Colab? ¿cuánto pesa el shard más grande?).
- Que el archivo de la LoRA Lightning que usa local_qwen.py existe.
- Qué proveedores sirven Qwen-Image-Edit para image-to-image (la prueba de
  coste irá contra el que elija "auto").

Salida: results_colab_check/report.md
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent))

import local_qwen  # noqa: E402

OUT = HERE.parent / "results_colab_check"


def main() -> int:
    from huggingface_hub import HfApi

    OUT.mkdir(exist_ok=True)
    api = HfApi(token=os.environ.get("HF_TOKEN") or None)
    lines = ["# Comprobación en el Hub para el notebook de Colab", ""]
    info = api.model_info(local_qwen.MODEL, files_metadata=True)
    by_dir, biggest = defaultdict(int), defaultdict(int)
    for s in info.siblings:
        d = s.rfilename.split("/")[0] if "/" in s.rfilename else "(raíz)"
        by_dir[d] += s.size or 0
        biggest[d] = max(biggest[d], s.size or 0)
    lines += [f"## `{local_qwen.MODEL}` (licencia: {getattr(info.card_data, 'license', '?')})", "",
              "| Parte | Tamaño total | Archivo más grande |", "|---|---|---|",
              *[f"| {d} | {by_dir[d] / 2**30:.1f} GB | {biggest[d] / 2**30:.2f} GB |" for d in sorted(by_dir)], "",
              f"Total: {sum(by_dir.values()) / 2**30:.1f} GB.", ""]

    files = api.list_repo_files(local_qwen.LIGHTNING_REPO)
    edit = sorted(f for f in files if "Edit" in f and f.endswith(".safetensors"))
    ok = local_qwen.LIGHTNING_FILE in files
    lines += [f"## LoRA Lightning (`{local_qwen.LIGHTNING_REPO}`)", "",
              f"- Archivo usado: `{local_qwen.LIGHTNING_FILE}` → **{'existe' if ok else 'NO EXISTE'}**.",
              "- Variantes para Edit disponibles:", *[f"  - `{f}`" for f in edit], ""]
    try:
        lic = api.model_info(local_qwen.LIGHTNING_REPO).card_data
        lines.append(f"- Licencia: {getattr(lic, 'license', '?')}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"- Licencia: no se pudo leer ({type(exc).__name__})")

    try:
        m = api.model_info(local_qwen.MODEL, expand=["inferenceProviderMapping"])
        provs = [f"{x.provider} ({x.status}, {x.task})" for x in (m.inference_provider_mapping or [])]
    except Exception as exc:  # noqa: BLE001
        provs = [f"error: {type(exc).__name__}"]
    lines += ["", "## Proveedores (Inference Providers)", "", *[f"- {p}" for p in provs]]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
