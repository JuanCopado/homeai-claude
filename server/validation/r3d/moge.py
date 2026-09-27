"""Una foto → geometría métrica con cámara estimada (MoGe-2, Microsoft) → nube de puntos."""

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))
from r3d.common import Timer, fail, photos, save  # noqa: E402

MODEL = "Ruicheng/moge-2-vitl-normal"


def main():
    import torch
    from moge.model.v2 import MoGeModel

    model = MoGeModel.from_pretrained(MODEL).eval()
    for p in photos("single"):
        try:
            img = Image.open(p).convert("RGB")
            x = torch.tensor(np.asarray(img) / 255, dtype=torch.float32).permute(2, 0, 1)
            with Timer() as t, torch.no_grad():
                out = model.infer(x)
            pts = out["points"].cpu().numpy().reshape(-1, 3)
            mask = out["mask"].cpu().numpy().reshape(-1).astype(bool)
            k = out["intrinsics"].cpu().numpy()
            fov = float(np.degrees(2 * np.arctan(0.5 / k[0, 0]))) if k[0, 0] < 5 else None
            depth = out["depth"].cpu().numpy()
            save("moge2", p.stem, pts[mask], np.asarray(img).reshape(-1, 3)[mask], t.s,
                 {"model": MODEL, "fov_estimado": round(fov, 1) if fov else None,
                  "profundidad_mediana_m": round(float(np.nanmedian(depth[np.isfinite(depth)])), 2)})
        except Exception as exc:  # noqa: BLE001
            fail("moge2", p.stem, exc)


if __name__ == "__main__":
    main()
