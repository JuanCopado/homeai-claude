"""Comprueba qué proveedores de Hugging Face sirven un modelo para image-to-image.

Uso (con HF_TOKEN en el entorno):
    python check_model.py stabilityai/stable-diffusion-xl-base-1.0

Ejecutar antes de cambiar HF_MODEL: si ningún proveedor sirve el modelo para
"image-to-image", el servicio devolverá model_unsupported.
"""

import os
import sys

from huggingface_hub import HfApi

model = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("HF_MODEL", "stabilityai/stable-diffusion-xl-base-1.0")
info = HfApi(token=os.environ.get("HF_TOKEN") or None).model_info(model, expand=["inferenceProviderMapping"])
mapping = info.inference_provider_mapping or []
rows = [m for m in mapping if getattr(m, "task", None) == "image-to-image"]
if not rows:
    print(f"{model}: ningún proveedor lo sirve para image-to-image.")
    others = sorted({getattr(m, "task", "?") for m in mapping})
    if others:
        print("  Tareas disponibles para este modelo:", ", ".join(others))
    sys.exit(1)
for m in rows:
    print(f"{model}: {m.provider} ({getattr(m, 'status', '?')})")
