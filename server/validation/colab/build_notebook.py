"""Genera los notebooks de medición (Colab y Kaggle) incrustando el código del
servidor tal cual.

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
OUT_KAGGLE = HERE / "qwen_edit_kaggle.ipynb"
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


KAGGLE_INTRO = """# HomeAI · Medición de Qwen-Image-Edit en Kaggle (GPU gratuita)

Ejecuta el pipeline de generación de HomeAI **con el mismo código que el servidor**
(instrucción de edición → 2 variantes → filtro de similitud antes del puntuador →
regeneración de las casi idénticas → puntuador estético → la mejor) en una GPU
gratuita de Kaggle. No gasta crédito de Hugging Face y **no necesita ningún token**.

**Cómo usarlo**
1. Panel derecho → *Session options*: **Accelerator → GPU T4 x2** e **Internet → On**
   (Internet exige tener el teléfono verificado en la cuenta de Kaggle).
2. Arriba a la derecha: **Save Version → Save & Run All (Commit) → Save**. Se ejecuta
   solo en segundo plano (hasta 12 h): **puedes cerrar la pestaña**.
3. Cuando termine, abre esa versión → pestaña **Output** → descarga `qa_qwen.zip` y
   pásaselo a Claude (o súbelo a `server/validation/` en la rama `claude/pipeline-qwen`).

**Qué hace**: descarga ~54 GB de pesos (Qwen2.5-VL 7B + transformer de 20B) y los carga
en 4 bits en dos fases, borrando del disco lo que ya usó. 10 fotos reales × 2 variantes
(+ las regeneradas) con la LoRA *Lightning* (8 pasos) y SDXL como referencia. Si algo
falla a mitad, el informe se escribe igualmente con lo medido hasta ahí.
"""

KAGGLE_SETUP = """import os, shutil
# Caché de Hugging Face en el disco con más espacio (/kaggle/working solo guarda 20 GB).
cands = [d for d in ("/kaggle/tmp", "/tmp") if os.path.isdir(d)]
best = max(cands, key=lambda d: shutil.disk_usage(d).free)
os.environ["HF_HOME"] = os.path.join(best, "hf")
for d in cands + ["/kaggle/working"]:
    print(f"{d}: {shutil.disk_usage(d).free / 2**30:.0f} GB libres")
print("Caché de modelos en", os.environ["HF_HOME"], "(hacen falta ~42 GB a la vez)")
!nvidia-smi --query-gpu=name,memory.total --format=csv
!pip install -q "diffusers>=0.35" "transformers>=4.51" "accelerate>=1.0" "bitsandbytes>=0.46" "peft>=0.17"
"""

KAGGLE_RUN = """import measure
data = measure.run("/kaggle/working/qa_qwen", variants=VARIANTS, lightning=LIGHTNING, sdxl=SDXL)"""

KAGGLE_REPORT = """from IPython.display import Markdown, display
import shutil
display(Markdown(open("/kaggle/working/qa_qwen/report.md", encoding="utf-8").read().split("La comparación subjetiva")[0]))
shutil.make_archive("/kaggle/working/qa_qwen", "zip", "/kaggle/working/qa_qwen")
print("Listo: descarga qa_qwen.zip desde la pestaña Output de esta versión.")"""


def cell(kind: str, src: str) -> dict:
    c = {"cell_type": kind, "metadata": {}, "source": src.splitlines(keepends=True)}
    if kind == "code":
        c.update(execution_count=None, outputs=[])
    return c


def build(target: str = "colab") -> str:
    kaggle = target == "kaggle"
    cells = [cell("markdown", KAGGLE_INTRO if kaggle else INTRO), cell("code", KAGGLE_SETUP if kaggle else SETUP),
             cell("markdown", "## Código del servidor de HomeAI (generado desde el repositorio, no editar aquí)")]
    for m in MODULES:
        cells.append(cell("code", f"%%writefile {m.name}\n" + m.read_text(encoding="utf-8")))
    cells += [cell("markdown", "## Configuración"), cell("code", CONFIG),
              cell("markdown", "## Medición"), cell("code", KAGGLE_RUN if kaggle else RUN),
              cell("markdown", "## Informe y descarga"), cell("code", KAGGLE_REPORT if kaggle else REPORT)]
    meta = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"}}
    if kaggle:
        meta["kaggle"] = {"accelerator": "nvidiaTeslaT4", "isInternetEnabled": True, "isGpuEnabled": True}
    else:
        meta.update(accelerator="GPU", colab={"gpuType": "T4", "provenance": []})
    nb = {"cells": cells, "metadata": meta, "nbformat": 4, "nbformat_minor": 4 if kaggle else 0}
    return json.dumps(nb, ensure_ascii=False, indent=1) + "\n"


def main() -> int:
    outs = {OUT: build("colab"), OUT_KAGGLE: build("kaggle")}
    if "--check" in sys.argv:
        stale = [p.name for p, text in outs.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        if stale:
            print(f"Notebooks no sincronizados ({', '.join(stale)}): ejecuta validation/colab/build_notebook.py")
            return 1
        print("Notebooks sincronizados con el código.")
        return 0
    for p, text in outs.items():
        p.write_text(text, encoding="utf-8")
        print(f"Escrito {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
