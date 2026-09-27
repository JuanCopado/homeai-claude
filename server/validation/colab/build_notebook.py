"""Genera qwen_edit_colab.ipynb incrustando el código del servidor tal cual.

El notebook no clona el repositorio (así funciona aunque sea privado y sin
tokens): cada módulo se escribe con %%writefile desde estas mismas fuentes.
CI comprueba que el notebook está sincronizado con el código:

    python validation/colab/build_notebook.py          (desde server/)
    python validation/colab/build_notebook.py --check
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
SERVER = HERE.parent.parent
OUT = HERE / "qwen_edit_colab.ipynb"
MODULES = [SERVER / "pipeline.py", SERVER / "segmentation.py", SERVER / "style.py", SERVER / "quality.py",
           SERVER / "local_qwen.py", HERE / "measure.py"]

INTRO = """# HomeAI · Medición de Qwen-Image-Edit en Colab (GPU gratuita)

Ejecuta el pipeline de generación de HomeAI **con el mismo código que el servidor**
(instrucción de edición → 2 variantes → filtro de similitud antes del puntuador →
regeneración de las casi idénticas → puntuador estético → la mejor), pero con el
modelo en la GPU de Colab en lugar de la Inference API de pago. No gasta crédito
de Hugging Face y **no necesita ningún token**.

**Cómo usarlo**
1. *Entorno de ejecución → Cambiar tipo de entorno de ejecución → **GPU T4*** → Guardar.
2. *Entorno de ejecución → **Ejecutar todo***. No hay que tocar nada más.
3. Al final se descarga `qa_qwen.zip` (informe, datos y rejillas). Súbelo a
   `server/validation/results_colab/` del repositorio o pásaselo a Claude.

**Qué hace y cuánto tarda (estimación, se mide al ejecutarlo)**
- Descarga ~54 GB de pesos (codificador Qwen2.5-VL 7B + transformer de 20B) y los
  carga **en 4 bits** para que quepan en los 16 GB de la T4, en dos fases (primero
  codifica todas las instrucciones, luego genera), borrando de disco lo que ya usó.
- 10 fotos reales × 2 variantes = 20 generaciones (+ las regeneradas), con la
  LoRA *Lightning* (8 pasos). Después, SDXL sobre las mismas fotos como referencia.
- Si Colab se desconecta, vuelve a *Ejecutar todo*: empieza de cero.
- ¿Se queda sin memoria o sale todo negro? Cambia `QWEN_DTYPE` en la celda de
  configuración y vuelve a ejecutar; el informe dice qué falló.
"""

SETUP = """!nvidia-smi --query-gpu=name,memory.total --format=csv
!pip install -q "diffusers>=0.35" "transformers>=4.51" "accelerate>=1.0" "bitsandbytes>=0.46" "peft>=0.17"
import shutil
print(f"Disco libre: {shutil.disk_usage('/content').free / 2**30:.0f} GB (hacen falta ~45 GB a la vez)")"""

CONFIG = """import os
VARIANTS = 2        # variantes por foto (el máximo del servidor)
LIGHTNING = True    # LoRA Lightning: 8 pasos sin CFG. False = 30 pasos con CFG (unas 8 veces más lento)
SDXL = True         # referencia SDXL sobre las mismas fotos
os.environ["QWEN_DTYPE"] = "auto"   # auto: fp16 en T4, bf16 en L4/A100. Prueba "bf16" si salen imágenes negras.
os.environ["TOKENIZERS_PARALLELISM"] = "false"
"""

RUN = """import measure
data = measure.run("qa_qwen", variants=VARIANTS, lightning=LIGHTNING, sdxl=SDXL)"""

REPORT = """from IPython.display import Markdown, display
import shutil
display(Markdown(open("qa_qwen/report.md", encoding="utf-8").read().split("La comparación subjetiva")[0]))
shutil.make_archive("qa_qwen", "zip", "qa_qwen")
try:
    from google.colab import files
    files.download("qa_qwen.zip")
except ImportError:
    print("Resultados en qa_qwen.zip")"""


def cell(kind: str, src: str) -> dict:
    c = {"cell_type": kind, "metadata": {}, "source": src.splitlines(keepends=True)}
    if kind == "code":
        c.update(execution_count=None, outputs=[])
    return c


def build() -> str:
    cells = [cell("markdown", INTRO), cell("code", SETUP),
             cell("markdown", "## Código del servidor de HomeAI (generado desde el repositorio, no editar aquí)")]
    for m in MODULES:
        cells.append(cell("code", f"%%writefile {m.name}\n" + m.read_text(encoding="utf-8")))
    cells += [cell("markdown", "## Configuración"), cell("code", CONFIG),
              cell("markdown", "## Medición"), cell("code", RUN),
              cell("markdown", "## Informe y descarga"), cell("code", REPORT)]
    nb = {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"gpuType": "T4", "provenance": []},
                                       "kernelspec": {"display_name": "Python 3", "name": "python3"},
                                       "language_info": {"name": "python"}},
          "nbformat": 4, "nbformat_minor": 0}
    return json.dumps(nb, ensure_ascii=False, indent=1) + "\n"


def main() -> int:
    text = build()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("qwen_edit_colab.ipynb no está sincronizado: ejecuta validation/colab/build_notebook.py")
            return 1
        print("Notebook sincronizado con el código.")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"Escrito {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
