"""Varias variantes por petición: filtro de similitud (antes del puntuador),
regeneración de las casi idénticas, puntuador y elección. El generador, CLIP y
el puntuador son dobles: aquí se prueba el reparto, los descartes, la
regeneración y el formato; la calibración real está en server/validation/."""

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


# Según el color de la variante: (score estético, similitud CLIP con el original).
# (181, 170, 160) es casi el original (180, 170, 160).
SCORES = {(250, 0, 0): (0.9, 0.7), (0, 250, 0): (0.7, 0.7), (0, 0, 250): (0.3, 0.7), (181, 170, 160): (0.8, 0.99)}
scored = []


def lookup(img):
    c = img.convert("RGB").getpixel((400, 300))
    return SCORES[min(SCORES, key=lambda k: sum(abs(a - b) for a, b in zip(k, c)))]


def fake_score(img):
    scored.append(img.convert("RGB").getpixel((400, 300)))
    return {"score": lookup(img)[0], "aesthetic": 5.0, "realism": 0.9}


def fake_similarity(img, original, box=None):
    return lookup(img)[1]


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "100")
    monkeypatch.setattr(quality, "score", fake_score)
    monkeypatch.setattr(quality, "similarity", fake_similarity)
    scored.clear()
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


def test_near_identical_is_regenerated_before_scoring(api, monkeypatch):
    gen = use(monkeypatch, Gen([(181, 170, 160), (0, 250, 0), (250, 0, 0)]))  # la 1.ª es casi el original
    body = post(api, 2).json()
    assert gen.calls == 3 and body["regenerated"] == 1 and body["retried"]
    v = body["variants"]
    assert v[0]["discarded"] and v[0]["reason"] == "sin_cambios" and v[0]["similarity"] == 0.99
    assert v[0]["score"] is None  # el puntuador no se gasta en ella
    assert len(scored) == 2 and all(c[:2] != (181, 170) for c in scored)
    assert body["best"] == 2 and v[2]["score"] == 0.9 and not body["low_quality"]


def test_regeneration_that_is_again_identical_shows_the_other(api, monkeypatch):
    gen = use(monkeypatch, Gen([(181, 170, 160), (0, 250, 0), (181, 170, 160)]))
    body = post(api, 2).json()
    assert gen.calls == 3 and [v["reason"] for v in body["variants"]] == ["sin_cambios", None, "sin_cambios"]
    assert body["best"] == 1


def test_all_identical_regenerates_each_once_then_shows_least_similar(api, monkeypatch):
    gen = use(monkeypatch, Gen([(181, 170, 160)]))
    body = post(api, 2).json()
    assert gen.calls == 4 and body["regenerated"] == 2 and body["low_quality"]
    assert not scored and all(v["reason"] == "sin_cambios" for v in body["variants"])


def test_low_quality_is_discarded_without_regenerating(api, monkeypatch):
    gen = use(monkeypatch, Gen([(0, 0, 250), (0, 250, 0)]))
    body = post(api, 2).json()
    assert gen.calls == 2 and not body["retried"]
    assert body["variants"][0]["reason"] == "calidad_baja" and body["best"] == 1


def test_all_low_quality_shows_best_available(api, monkeypatch):
    gen = use(monkeypatch, Gen([(0, 0, 250)]))  # siempre mala
    body = post(api, 2).json()
    assert gen.calls == 2 and body["low_quality"] and all(v["discarded"] for v in body["variants"])


def test_partial_failure_still_returns_the_rest(api, monkeypatch):
    use(monkeypatch, Gen([(250, 0, 0)], fail={1}))
    body = post(api, 2).json()
    assert len(body["variants"]) == 1 and body["best"] == 0


def test_all_failed_returns_the_error(api, monkeypatch):
    use(monkeypatch, Gen([(250, 0, 0)], fail={0, 1}))
    r = post(api, 2)
    assert r.status_code == 502 and r.json()["error"] == "model_unsupported"
    assert service._active == 0


def test_variants_are_capped_at_two(api, monkeypatch):
    monkeypatch.setenv("VARIANTS_MAX", "3")  # aunque se configure más, el máximo es 2
    gen = use(monkeypatch, Gen([(250, 0, 0)]))
    assert len(post(api, 9).json()["variants"]) == 2 and gen.calls == 2


def test_each_variant_counts_towards_rate_limit(api, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "3")
    use(monkeypatch, Gen([(250, 0, 0)]))
    assert post(api, 2).status_code == 200
    r = post(api, 2)  # 2 + 2 > 3
    assert r.status_code == 429 and r.json()["error"] == "rate_limited"


def test_regeneration_without_quota_shows_best_available(api, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "2")
    gen = use(monkeypatch, Gen([(181, 170, 160), (0, 250, 0)]))
    body = post(api, 2).json()
    assert gen.calls == 2 and not body["retried"] and body["best"] == 1


def test_scorer_failure_returns_unfiltered(api, monkeypatch):
    def broken(img):
        raise RuntimeError("sin pesos del predictor estético")

    monkeypatch.setattr(quality, "score", broken)
    use(monkeypatch, Gen([(0, 250, 0), (250, 0, 0)]))
    body = post(api, 2).json()
    assert len(body["variants"]) == 2 and not any(v["discarded"] for v in body["variants"])


def test_similarity_failure_skips_the_filter(api, monkeypatch):
    def broken(img, original, box=None):
        raise RuntimeError("sin CLIP")

    monkeypatch.setattr(quality, "similarity", broken)
    gen = use(monkeypatch, Gen([(181, 170, 160), (250, 0, 0)]))
    body = post(api, 2).json()
    assert gen.calls == 2 and body["best"] == 1 and not body["variants"][1]["discarded"]


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


def test_zone_similarity_is_measured_on_the_zone_crop(api, monkeypatch):
    seen = []

    def spy(img, original, box=None):
        seen.append(box)
        return fake_similarity(img, original)

    monkeypatch.setattr(quality, "similarity", spy)
    use(monkeypatch, Gen([(250, 0, 0), (0, 250, 0)]))
    mask = np.zeros((600, 800), bool)
    mask[420:, 100:300] = True
    buf = io.BytesIO()
    Image.fromarray((mask * 255).astype(np.uint8), "L").save(buf, format="PNG")
    post(api, 2, buf.getvalue())
    assert seen and all(b == (92, 412, 308, 600) for b in seen)  # caja de la zona + 8 px


def test_when_all_discarded_prefers_low_quality_over_unchanged():
    v = [{"score": 0.9, "similarity": 0.99, "discarded": True, "reason": "sin_cambios"},
         {"score": 0.4, "discarded": True, "reason": "calidad_baja"},
         {"score": 0.3, "discarded": True, "reason": "calidad_baja"}]
    assert service.pick_best(v) == 1
    v.append({"score": 0.6, "discarded": False, "reason": None})
    assert service.pick_best(v) == 3


def test_all_unchanged_shows_the_least_similar():
    v = [{"similarity": 0.999, "discarded": True, "reason": "sin_cambios"},
         {"similarity": 0.91, "discarded": True, "reason": "sin_cambios"}]
    assert service.pick_best(v) == 1


def test_default_thresholds_and_model():
    cfg = service.settings()
    assert (cfg["min_score"], cfg["max_similarity"], cfg["variants_max"]) == (0.5, 0.89, 2)
    assert cfg["model"] == "Qwen/Qwen-Image-Edit" and cfg["backend"] == "api"
