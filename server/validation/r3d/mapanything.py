"""Varias fotos de la misma estancia → nube métrica conjunta con poses de cámara
(MapAnything, checkpoint Apache-2.0). También se prueba con UNA sola foto."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from r3d.common import INPUT, Timer, fail, photos, save  # noqa: E402

MODEL = "facebook/map-anything-apache"


def run(model, load_images, folder, case):
    import torch

    try:
        views = load_images(str(folder))
        with Timer() as t, torch.no_grad():
            preds = model.infer(views, memory_efficient_inference=True, use_amp=False, apply_mask=True, mask_edges=True)
        xyz, rgb = [], []
        pose0_inv = np.linalg.inv(preds[0]["camera_poses"][0].cpu().numpy())
        for v, pr in zip(views, preds):
            pts = pr["pts3d"][0].cpu().numpy().reshape(-1, 3)
            m = pr["mask"][0].cpu().numpy().reshape(-1).astype(bool)
            pts = (np.c_[pts, np.ones(len(pts))] @ pose0_inv.T)[:, :3]  # a la cámara de la 1.ª foto
            img = v["img"][0].cpu().numpy()
            if img.shape[0] == 3:
                img = img.transpose(1, 2, 0)
            img = img.reshape(-1, 3)
            img = ((img - img.min()) / (img.max() - img.min() + 1e-6) * 255).astype(np.uint8)
            xyz.append(pts[m])
            rgb.append(img[m])
        save("mapanything_apache", case, np.concatenate(xyz), np.concatenate(rgb), t.s,
             {"model": MODEL, "vistas": len(views)})
    except Exception as exc:  # noqa: BLE001
        fail("mapanything_apache", case, exc)


def main():
    import shutil

    from mapanything.models import MapAnything
    from mapanything.utils.image import load_images

    model = MapAnything.from_pretrained(MODEL).eval()
    run(model, load_images, INPUT / "multi", "multi")
    for p in photos("single")[:1]:
        tmp = INPUT / f"_one_{p.stem}"
        tmp.mkdir(exist_ok=True)
        shutil.copy(p, tmp / p.name)
        run(model, load_images, tmp, f"single_{p.stem}")
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
