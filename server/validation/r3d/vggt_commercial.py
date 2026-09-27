"""Varias fotos → nube conjunta (VGGT-1B-Commercial, Meta). El checkpoint está
restringido en Hugging Face: hay que solicitar acceso con la cuenta del token."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from r3d.common import Timer, fail, photos, save  # noqa: E402

MODEL = "facebook/VGGT-1B-Commercial"


def main():
    import torch

    try:
        from vggt.models.vggt import VGGT
        from vggt.utils.load_fn import load_and_preprocess_images

        model = VGGT.from_pretrained(MODEL).eval()
    except Exception as exc:  # noqa: BLE001 - p. ej. acceso restringido (gated)
        fail("vggt_1b_commercial", "multi", exc)
        return
    files = [str(p) for p in photos("multi")]
    try:
        images = load_and_preprocess_images(files)
        with Timer() as t, torch.no_grad():
            pred = model(images)
        wp = pred["world_points"][0].cpu().numpy()  # (S, H, W, 3)
        conf = pred["world_points_conf"][0].cpu().numpy()
        cols = images.cpu().numpy().transpose(0, 2, 3, 1)
        keep = conf > np.percentile(conf, 40)
        save("vggt_1b_commercial", "multi", wp[keep], (cols[keep] * 255).astype(np.uint8), t.s,
             {"model": MODEL, "vistas": len(files)})
    except Exception as exc:  # noqa: BLE001
        fail("vggt_1b_commercial", "multi", exc)


if __name__ == "__main__":
    main()
