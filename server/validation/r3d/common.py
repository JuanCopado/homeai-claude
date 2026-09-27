"""Utilidades compartidas por las pruebas de reconstrucción 3D (research, no producción).

- Fotos de entrada en results_3d/input/{single,multi}/ (las descarga fetch.py).
- render(): proyecta una nube de puntos desde la cámara original y desde dos
  puntos de vista nuevos; es donde se ven los defectos de una reconstrucción.
- save(): guarda nube (GLB, submuestreada), renders y un JSON de resultado.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).parent
OUT = HERE.parent / "results_3d"
INPUT = OUT / "input"


def photos(kind: str) -> list[Path]:
    return sorted((INPUT / kind).glob("*.jpg"))


def _rot(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    y, p = np.radians(yaw_deg), np.radians(pitch_deg)
    ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    rx = np.array([[1, 0, 0], [0, np.cos(p), -np.sin(p)], [0, np.sin(p), np.cos(p)]])
    return rx @ ry


def render(xyz: np.ndarray, rgb: np.ndarray, size: int = 420) -> Image.Image:
    """xyz en coordenadas de cámara (x derecha, y abajo, z hacia delante)."""
    ok = np.isfinite(xyz).all(1) & (xyz[:, 2] > 1e-3)
    xyz, rgb = xyz[ok], rgb[ok]
    center = np.median(xyz, axis=0)
    panels = []
    for name, yaw, pitch, back in (("vista original", 0, 0, 0.0), ("girada 30°", 30, 0, 0.15), ("desde arriba 35°", -20, 35, 0.3)):
        p = (xyz - center) @ _rot(yaw, pitch).T
        p[:, 2] += center[2] * (1 + back)
        keep = p[:, 2] > 1e-3
        p, c = p[keep], rgb[keep]
        f = size * 0.9
        u = (p[:, 0] / p[:, 2] * f + size / 2).astype(int)
        v = (p[:, 1] / p[:, 2] * f + size / 2).astype(int)
        inside = (u >= 0) & (u < size) & (v >= 0) & (v < size)
        u, v, z, c = u[inside], v[inside], p[inside, 2], c[inside]
        order = np.argsort(-z)  # de lejos a cerca: los cercanos tapan
        img = np.full((size, size, 3), 245, np.uint8)
        for du in (0, 1):
            for dv in (0, 1):
                uu, vv = np.clip(u[order] + du, 0, size - 1), np.clip(v[order] + dv, 0, size - 1)
                img[vv, uu] = c[order]
        pil = Image.fromarray(img)
        ImageDraw.Draw(pil).text((6, 4), name, fill=(0, 0, 0))
        panels.append(pil)
    canvas = Image.new("RGB", (size * 3, size), "white")
    for i, pnl in enumerate(panels):
        canvas.paste(pnl, (i * size, 0))
    return canvas


def save(method: str, case: str, xyz: np.ndarray, rgb: np.ndarray, seconds: float, extra: dict | None = None):
    import trimesh

    d = OUT / method
    d.mkdir(parents=True, exist_ok=True)
    ok = np.isfinite(xyz).all(1)
    xyz, rgb = xyz[ok], rgb[ok]
    idx = np.random.default_rng(0).choice(len(xyz), size=min(len(xyz), 120_000), replace=False)
    trimesh.PointCloud(xyz[idx], colors=np.c_[rgb[idx], np.full(len(idx), 255)]).export(d / f"{case}.glb")
    render(xyz, rgb).save(d / f"{case}.jpg", quality=85)
    res = {"method": method, "case": case, "ok": True, "seconds": round(seconds, 1), "points": int(len(xyz))}
    res.update(extra or {})
    (d / f"{case}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False))


def fail(method: str, case: str, err: BaseException, seconds: float = 0.0):
    d = OUT / method
    d.mkdir(parents=True, exist_ok=True)
    res = {"method": method, "case": case, "ok": False, "seconds": round(seconds, 1), "error": f"{type(err).__name__}: {str(err)[:400]}"}
    (d / f"{case}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False))


class Timer:
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *a):
        self.s = time.perf_counter() - self.t0


def unproject(depth: np.ndarray, fov_deg: float = 60.0) -> np.ndarray:
    h, w = depth.shape
    f = (w / 2) / np.tan(np.radians(fov_deg) / 2)
    ys, xs = np.mgrid[0:h, 0:w]
    return np.stack([(xs - w / 2) / f * depth, (ys - h / 2) / f * depth, depth], -1).reshape(-1, 3)
