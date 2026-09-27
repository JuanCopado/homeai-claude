"""Segmentación por zonas y generación con máscara. El modelo de segmentación y
el de generación se sustituyen por dobles: aquí se prueba el código propio
(mapeo de zonas, máscaras, composición, API); la calidad del modelo real se
validó aparte (server/validation/)."""

import base64
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageFilter

import app as service
import segmentation as seg

W, H = 800, 600  # tamaño de la foto de prueba; múltiplo de 8, no se redimensiona


def photo(color=(180, 170, 160)):
    buf = io.BytesIO()
    Image.new("RGB", (W, H), color).save(buf, format="PNG")
    return buf.getvalue()


def fake_zmap(w, h):
    """Techo arriba, suelo abajo, pared en medio, una "cama" a la izquierda."""
    z = np.zeros((h, w), dtype=np.uint8)  # pared
    z[: h // 5] = seg.ZONE_ORDER.index("techo")
    z[int(h * 0.7):] = seg.ZONE_ORDER.index("suelo")
    z[int(h * 0.5): int(h * 0.85), : w // 3] = seg.ZONE_ORDER.index("mobiliario")
    return z


def erode(mask, px):
    """Máscara reducida px píxeles (zona interior, lejos del borde suavizado)."""
    return np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(2 * px + 1))) > 127


def dilate(mask, px):
    return np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(2 * px + 1))) > 127


def png_mask(mask):
    buf = io.BytesIO()
    Image.fromarray((mask * 255).astype(np.uint8), mode="L").save(buf, format="PNG")
    return buf.getvalue()


class FakeGen:
    def __init__(self):
        self.calls = []

    def image_to_image(self, image, **kwargs):
        self.calls.append(kwargs)
        return Image.new("RGB", Image.open(io.BytesIO(image)).size, (20, 200, 40))


@pytest.fixture
def env(monkeypatch):
    gen = FakeGen()
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "100")
    monkeypatch.setattr(service, "make_client", lambda cfg: gen)
    monkeypatch.setattr(seg, "load_segmenter", lambda: (lambda img: fake_zmap(*img.size)))
    service._hits.clear()
    service._active = service._seg_active = 0
    return gen


@pytest.fixture
def api():
    return TestClient(service.app)


# --- mapeo de zonas --------------------------------------------------------------

@pytest.mark.parametrize(
    "label,zone",
    [("wall", "pared"), ("column", "pared"), ("floor", "suelo"), ("ceiling", "techo"), ("bed ", "mobiliario"),
     ("kitchen island", "mobiliario"), ("windowpane", "ventana/puerta"), ("door", "ventana/puerta"),
     ("mirror", "otros"), ("sky", "otros")],
)
def test_zone_of(label, zone):
    assert seg.zone_of(label) == zone


# --- composición -------------------------------------------------------------------

def test_composite_never_leaks_outside_mask():
    rng = np.random.default_rng(0)
    original = Image.fromarray(rng.integers(0, 255, (H, W, 3), dtype=np.uint8))
    generated = Image.new("RGB", (W, H), (0, 255, 0))
    mask = fake_zmap(W, H) == seg.ZONE_ORDER.index("suelo")
    out = np.asarray(seg.composite(original, generated, mask))
    orig = np.asarray(original)
    assert np.array_equal(out[~mask], orig[~mask])  # fuera: idéntico píxel a píxel
    assert np.all(out[erode(mask, 15)] == [0, 255, 0])  # dentro, lejos del borde: el resultado del modelo


def test_composite_with_several_zones_and_resized_result():
    original = Image.new("RGB", (W, H), (100, 100, 100))
    generated = Image.new("RGB", (512, 384), (255, 0, 0))  # el modelo devuelve otro tamaño
    z = fake_zmap(W, H)
    mask = np.isin(z, [seg.ZONE_ORDER.index("pared"), seg.ZONE_ORDER.index("techo")])
    out = np.asarray(seg.composite(original, generated, mask))
    assert out.shape == (H, W, 3)
    assert np.all(out[~mask] == 100)
    assert tuple(out[H // 10, W // 2]) == (255, 0, 0)  # techo
    assert tuple(out[int(H * 0.4), W // 2]) == (255, 0, 0)  # pared


def test_parse_mask_resizes_and_thresholds():
    m = seg.parse_mask(Image.new("L", (400, 300), 200), (W, H))
    assert m.shape == (H, W) and m.all()


# --- /api/segment ------------------------------------------------------------------

def test_segment_returns_map_and_zones_without_token(api, env, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)  # segmentar no gasta crédito de HF
    r = api.post("/api/segment", files={"image": ("a.png", photo(), "image/png")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["width"], body["height"]) == (W, H)
    assert r.headers["cache-control"] == "no-store"
    pct = {z["zone"]: z["pct"] for z in body["zones"]}
    assert abs(sum(pct.values()) - 100) < 0.5 and pct["mobiliario"] > 5
    assert [z["zone"] for z in body["zones"] if z["selectable"]] == seg.SELECTABLE
    raw = base64.b64decode(body["map"].split(",", 1)[1])
    decoded = np.round(np.asarray(Image.open(io.BytesIO(raw))) / body["step"]).astype(np.uint8)
    expected = np.asarray(Image.fromarray(fake_zmap(W, H)).filter(seg.ImageFilter.ModeFilter(5)))
    assert np.array_equal(decoded, expected)


def test_segment_rejects_bad_images(api, env):
    r = api.post("/api/segment", files={"image": ("a.heic", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 99, "image/heic")})
    assert r.status_code == 415


def test_segment_model_failure_is_reported(api, env, monkeypatch):
    def broken():
        raise RuntimeError("no se pudo descargar el modelo")

    monkeypatch.setattr(seg, "load_segmenter", broken)
    r = api.post("/api/segment", files={"image": ("a.png", photo(), "image/png")})
    assert r.status_code == 503 and r.json()["error"] == "segmentation_unavailable"
    assert service._seg_active == 0


def test_segment_rate_limit_is_separate_from_generation(api, env, monkeypatch):
    monkeypatch.setenv("SEG_RATE_LIMIT_PER_HOUR", "1")
    assert api.post("/api/segment", files={"image": ("a.png", photo(), "image/png")}).status_code == 200
    assert api.post("/api/segment", files={"image": ("a.png", photo(), "image/png")}).status_code == 429
    r = api.post("/api/renovate", files={"image": ("a.png", photo(), "image/png")}, data={"style": "nórdico"})
    assert r.status_code == 200


# --- /api/renovate con máscara -----------------------------------------------------

def renovate(api, mask=None, zones="", style="madera clara"):
    files = {"image": ("a.png", photo((180, 170, 160)), "image/png")}
    if mask is not None:
        files["mask"] = ("mask.png", mask, "image/png")
    return api.post("/api/renovate", files=files, data={"style": style, "zones": zones})


def test_masked_generation_only_changes_selected_zone(api, env):
    mask = fake_zmap(W, H) == seg.ZONE_ORDER.index("suelo")
    r = renovate(api, png_mask(mask), "suelo")
    assert r.status_code == 200
    out = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"), dtype=int)
    # La composición es exacta (ver test_composite_never_leaks_outside_mask); lo
    # único que llega a la respuesta es la compresión JPEG, cuyo "eco" en un
    # borde artificial tan duro alcanza unos pocos píxeles. A 16 px del borde
    # no hay rastro del resultado del modelo.
    far_outside = ~dilate(mask, 16)
    assert np.abs(out[far_outside] - [180, 170, 160]).max() <= 6
    assert np.abs(out[erode(mask, 15)] - [20, 200, 40]).max() <= 6
    assert env.calls[0]["prompt"].startswith("the floor redesigned: madera clara")


def test_masked_generation_multiple_zones(api, env):
    z = fake_zmap(W, H)
    mask = np.isin(z, [seg.ZONE_ORDER.index("pared"), seg.ZONE_ORDER.index("mobiliario")])
    r = renovate(api, png_mask(mask), "pared,mobiliario")
    assert r.status_code == 200
    out = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"), dtype=int)
    assert np.abs(out[~dilate(mask, 16)] - [180, 170, 160]).max() <= 6
    assert np.abs(out[erode(mask, 15)] - [20, 200, 40]).max() <= 6
    assert "the walls and the furniture redesigned" in env.calls[0]["prompt"]


def test_mask_of_different_size_is_scaled(api, env):
    small = np.zeros((300, 400), bool)
    small[150:] = True
    assert renovate(api, png_mask(small), "suelo").status_code == 200


@pytest.mark.parametrize(
    "mask,zones,code",
    [
        (png_mask(np.zeros((H, W), bool)), "suelo", "empty_mask"),
        (b"no es una imagen", "suelo", "invalid_mask"),
        (None, "sotano", "invalid_zones"),
    ],
)
def test_bad_masks_and_zones(api, env, mask, zones, code):
    r = renovate(api, mask, zones)
    assert r.status_code == 400 and r.json()["error"] == code
    assert not env.calls


def test_jpeg_mask_is_rejected(api, env):
    buf = io.BytesIO()
    Image.new("L", (W, H), 255).save(buf, format="JPEG")
    assert renovate(api, buf.getvalue(), "suelo").json()["error"] == "invalid_mask"


def test_without_mask_behaves_as_before(api, env):
    r = renovate(api, None, "")
    assert r.status_code == 200
    assert env.calls[0]["prompt"].startswith("madera clara, same room")
