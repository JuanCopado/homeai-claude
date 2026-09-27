"""Una foto → profundidad relativa (Depth Anything V2 Small, Apache-2.0) → nube de puntos.
Sin escala real ni cámara estimada: se supone un campo de visión de 60°."""

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))
from r3d.common import Timer, fail, photos, save, unproject  # noqa: E402

MODEL = "depth-anything/Depth-Anything-V2-Small-hf"


def main():
    from transformers import pipeline

    pipe = pipeline("depth-estimation", model=MODEL, device=-1)
    for p in photos("single"):
        try:
            img = Image.open(p).convert("RGB")
            with Timer() as t:
                pred = pipe(img)["predicted_depth"]
            disp = np.asarray(pred.squeeze(), dtype=np.float32)
            disp = np.array(Image.fromarray(disp).resize(img.size, Image.BILINEAR))
            depth = 1.0 / np.clip(disp / disp.max(), 0.02, None)  # disparidad relativa → profundidad relativa
            xyz = unproject(depth)
            save("depth_anything_v2_small", p.stem, xyz, np.asarray(img).reshape(-1, 3), t.s,
                 {"model": MODEL, "note": "profundidad relativa; FOV supuesto 60°"})
        except Exception as exc:  # noqa: BLE001
            fail("depth_anything_v2_small", p.stem, exc)


if __name__ == "__main__":
    main()
