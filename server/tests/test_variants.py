"""Varias variantes por petición + filtro de calidad. El generador y el
puntuador son dobles: aquí se prueba el reparto, los descartes, el reintento
y el formato; la calibración real está en server/validation/."""

import base64
import io
import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app as service
import quality
import segmentation as seg


def photo():
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (180, 170, 160)).save(buf, format="PNG")
    return buf.getvalue()


class Gen:
    """Cada llamada devuelve un color distinto; opcionalmente falla o tarda."""

    def __init__(self, colors, fail=(), delay=0.0):
        self.colors, self.fail, self.delay = list(colors), set(fail), delay
        self.calls, self.lock, self.active, self.max_active = 0, threading.Lock(), 0, 0

    def image_to_image(self, image, **kwargs):
        with self.lock:
            i = self.calls
            self.calls += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(self.delay)
            if i in self.fail:
                raise ValueError("modelo sin proveedor")
            return Image.new("RGB", Image.open(io.BytesIO(image)).size, self.colors[i % len(self.colors)])
        finally:
            with self.lock:
                self.active -= 1


# Puntuación de prueba según el color de la variante: (score, change)
SCORES = {(250, 0, 0): (0.9, 0.3), (0, 250, 0): (0.7, 0.3), (0, 0, 250): (0.3, 0.3), (181, 170, 160): (0.8, 0.01)}


def fake_score(img, original=None, box=None):
    c = img.convert("RGB").getpixel((400, 300))
    key = min(SCORES, key=lambda k: sum(abs(a - b) for a, b in zip(k, c)))
    score, change = SCORES[key]
    return {"score": score, "aesthetic": 5.0, "realism": 0.9, "change": change}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "100")
    monkeypatch.setattr(quality, "score", fake_score)
    service._hits.clear()
    service._active = service._seg_active = 0
    return TestClient(service.app)


def use(monkeypatch, gen):
    monkeypatch.setattr(service, "make_client", lambda cfg: gen)
    return gen


def post(api, variants, mask=None):
    files = {"image": ("a.png", photo(), "image/png")}
    if mask is not None:
        files["mask"] = ("m.png", mask, "image/png")
    return api.post("/api/renovate", files=files, data={"style": "nórdico", "variants": str(variants),
                                                         "zones": "suelo" if mask is not None else ""})


def decode(v):
    return Image.open(io.BytesIO(base64.b64decode(v["image"].split(",", 1)[1]))).convert("RGB")


def test_single_variant_keeps_jpeg_response(api, monkeypatch):
    gen = use(monkeypatch, Gen([(250, 0, 0)]))
    r = post(api, 1)
    assert r.headers["content-type"] == "image/jpeg" and gen.calls == 1


def test_two_variants_in_parallel_best_first_choice(api, monkeypatch):
    gen = use(monkeypatch, Gen([(0, 250, 0), (250, 0, 0)], delay=0.3))
    t0 = time.perf_counter()
    r = post(api, 2)
    elapsed = time.perf_counter() - t0
    body = r.json()
    assert r.status_code == 200 and gen.calls == 2 and gen.max_active == 2
    assert elapsed < 0.55  # en paralelo: ~0,3 s, no 0,6 s
    assert body["best"] == 1 and body["variants"][1]["score"] == 0.9
    assert not body["retried"] and not body["low_quality"]
    assert decode(body["variants"][1]).getpixel((10, 10))[0] > 200


def test_variant_without_changes_is_discarded(api, monkeypatch):
    use(monkeypatch, Gen([(181, 170, 160), (0, 250, 0)]))  # la 1.ª es casi el original
    body = post(api, 2).json()
    assert body["variants"][0]["discarded"] and body["variants"][0]["reason"] == "sin_cambios"
    assert body["best"] == 1  # aunque la "sin cambios" tenga más nota (0,8 > 0,7)


def test_low_quality_is_discarded(api, monkeypatch):
    use(monkeypatch, Gen([(0, 0, 250), (0, 250, 0)]))
    body = post(api, 2).json()
    assert body["variants"][0]["reason"] == "calidad_baja" and body["best"] == 1


def test_all_bad_retries_once_then_shows_best_available(api, monkeypatch):
    gen = use(monkeypatch, Gen([(0, 0, 250)]))  # siempre mala
    body = post(api, 2).json()
    assert gen.calls == 4 and body["retried"] and body["low_quality"]
    assert len(body["variants"]) == 4 and all(v["discarded"] for v in body["variants"])


def test_retry_rescues_a_good_variant(api, monkeypatch):
    gen = use(monkeypatch, Gen([(0, 0, 250), (0, 0, 250), (250, 0, 0), (0, 0, 250)]))
    body = post(api, 2).json()
    assert gen.calls == 4 and body["retried"] and not body["low_quality"]
    assert body["variants"][body["best"]]["score"] == 0.9


def test_partial_failure_still_returns_the_rest(api, monkeypatch):
    use(monkeypatch, Gen([(250, 0, 0)], fail={1}))
    body = post(api, 2).json()
    assert len(body["variants"]) == 1 and body["best"] == 0


def test_all_failed_returns_the_error(api, monkeypatch):
    use(monkeypatch, Gen([(250, 0, 0)], fail={0, 1}))
    r = post(api, 2)
    assert r.status_code == 502 and r.json()["error"] == "model_unsupported"
    assert service._active == 0


def test_variants_are_capped(api, monkeypatch):
    gen = use(monkeypatch, Gen([(250, 0, 0)]))
    assert len(post(api, 9).json()["variants"]) == 3 and gen.calls == 3


def test_each_variant_counts_towards_rate_limit(api, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "3")
    use(monkeypatch, Gen([(250, 0, 0)]))
    assert post(api, 2).status_code == 200
    r = post(api, 2)  # 2 + 2 > 3
    assert r.status_code == 429 and r.json()["error"] == "rate_limited"


def test_retry_without_quota_shows_best_available(api, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "2")
    gen = use(monkeypatch, Gen([(0, 0, 250)]))
    body = post(api, 2).json()
    assert gen.calls == 2 and not body["retried"] and body["low_quality"]


def test_scorer_failure_returns_unfiltered(api, monkeypatch):
    def broken(img, original=None, box=None):
        raise RuntimeError("sin pesos del predictor estético")

    monkeypatch.setattr(quality, "score", broken)
    use(monkeypatch, Gen([(0, 250, 0), (250, 0, 0)]))
    body = post(api, 2).json()
    assert len(body["variants"]) == 2 and not any(v["discarded"] for v in body["variants"])


def test_mask_is_applied_to_every_variant(api, monkeypatch):
    use(monkeypatch, Gen([(250, 0, 0), (0, 250, 0)]))
    mask = np.zeros((600, 800), bool)
    mask[420:] = True
    buf = io.BytesIO()
    Image.fromarray((mask * 255).astype(np.uint8), "L").save(buf, format="PNG")
    body = post(api, 2, buf.getvalue()).json()
    for v in body["variants"]:
        out = np.asarray(decode(v), dtype=int)
        assert np.abs(out[:380] - [180, 170, 160]).max() <= 6  # fuera de la máscara, intacto


def test_zone_change_is_measured_on_the_zone_crop(api, monkeypatch):
    seen = []

    def spy(img, original=None, box=None):
        seen.append(box)
        return fake_score(img, original)

    monkeypatch.setattr(quality, "score", spy)
    use(monkeypatch, Gen([(250, 0, 0), (0, 250, 0)]))
    mask = np.zeros((600, 800), bool)
    mask[420:, 100:300] = True
    buf = io.BytesIO()
    Image.fromarray((mask * 255).astype(np.uint8), "L").save(buf, format="PNG")
    post(api, 2, buf.getvalue())
    assert seen and all(b == (92, 412, 308, 600) for b in seen)  # caja de la zona + 8 px


def test_when_all_discarded_prefers_low_quality_over_unchanged():
    v = [{"score": 0.9, "discarded": True, "reason": "sin_cambios"},
         {"score": 0.4, "discarded": True, "reason": "calidad_baja"},
         {"score": 0.3, "discarded": True, "reason": "calidad_baja"}]
    assert service.pick_best(v) == 1
    v.append({"score": 0.6, "discarded": False, "reason": None})
    assert service.pick_best(v) == 3


def test_all_unchanged_shows_the_one_that_changed_most():
    v = [{"score": 0.9, "change": 0.001, "discarded": True, "reason": "sin_cambios"},
         {"score": 0.6, "change": 0.09, "discarded": True, "reason": "sin_cambios"}]
    assert service.pick_best(v) == 1


def test_default_thresholds_are_the_calibrated_ones():
    cfg = service.settings()
    assert (cfg["min_score"], cfg["min_change"]) == (0.5, 0.11)


def test_default_model_is_served_one():
    assert service.settings()["model"] == "Qwen/Qwen-Image-Edit"
