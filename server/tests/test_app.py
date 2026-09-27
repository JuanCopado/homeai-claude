"""Tests del servicio de visualización. Nunca llaman a Hugging Face: el cliente
se sustituye por un doble que devuelve una imagen o lanza el error a probar."""

import io

import httpx
import pytest
from fastapi.testclient import TestClient
from huggingface_hub.errors import HfHubHTTPError, InferenceTimeoutError
from PIL import Image

import app as service


def jpeg(size=(800, 600), color=(180, 170, 160), exif=None, fmt="JPEG"):
    buf = io.BytesIO()
    img = Image.new("RGB" if fmt != "PNG" else "RGBA", size, color if fmt != "PNG" else color + (128,))
    kwargs = {"exif": exif} if exif is not None else {}
    img.save(buf, format=fmt, **kwargs)
    return buf.getvalue()


class FakeClient:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def image_to_image(self, image, **kwargs):
        self.calls.append((image, kwargs))
        if self.error:
            raise self.error
        src = Image.open(io.BytesIO(image))
        return Image.new("RGB", src.size, (40, 90, 60))


@pytest.fixture
def fake(monkeypatch):
    client = FakeClient()
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "100")
    monkeypatch.setattr(service, "make_client", lambda cfg: client)
    service._hits.clear()
    service._active = 0
    return client


@pytest.fixture
def api():
    return TestClient(service.app)


def post(api, data, style="nórdico, madera clara", strength=None, name="salon.jpg", ctype="image/jpeg"):
    form = {"style": style}
    if strength is not None:
        form["strength"] = str(strength)
    return api.post("/api/renovate", files={"image": (name, data, ctype)}, data=form)


def http_error(status):
    req = httpx.Request("POST", "https://router.huggingface.co/x")
    return HfHubHTTPError(f"HTTP {status}", response=httpx.Response(status, request=req))


def test_health_does_not_leak_token(api, fake):
    body = api.get("/api/health").json()
    assert body["configured"] is True
    assert "hf_test" not in str(body)


def test_missing_token_is_reported(api, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    r = post(api, jpeg())
    assert r.status_code == 503 and r.json()["error"] == "not_configured"


def test_success_returns_jpeg_and_sends_structure_prompt(api, fake):
    r = post(api, jpeg(), strength=0.9)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "no-store"
    assert Image.open(io.BytesIO(r.content)).format == "JPEG"
    _, kwargs = fake.calls[0]
    assert kwargs["prompt"].startswith("nórdico, madera clara, same room")
    assert kwargs["strength"] == 0.8  # se limita al máximo permitido
    assert kwargs["negative_prompt"]


def test_exif_and_gps_are_stripped_before_sending(api, fake):
    exif = Image.Exif()
    exif[0x8825] = {2: (40, 25, 0)}  # GPSInfo
    exif[0x0112] = 6  # Orientation: rotar 90°
    r = post(api, jpeg(size=(800, 600), exif=exif.tobytes()))
    assert r.status_code == 200
    sent = Image.open(io.BytesIO(fake.calls[0][0]))
    assert not sent.getexif()
    assert sent.size == (600, 800)  # la orientación se aplicó antes de quitar el EXIF


def test_large_photo_is_resized_to_multiple_of_8(api, fake):
    r = post(api, jpeg(size=(4000, 3001)))
    assert r.status_code == 200
    w, h = Image.open(io.BytesIO(fake.calls[0][0])).size
    assert max(w, h) <= 1024 and w % 8 == 0 and h % 8 == 0


def test_transparent_png_and_webp_are_accepted(api, fake):
    assert post(api, jpeg(fmt="PNG"), name="a.png", ctype="image/png").status_code == 200
    assert post(api, jpeg(fmt="WEBP"), name="a.webp", ctype="image/webp").status_code == 200


def test_dark_photo_is_brightened(api, fake):
    buf = io.BytesIO()
    img = Image.new("RGB", (600, 600), (8, 8, 8))
    img.paste((30, 30, 30), (100, 100, 300, 500))  # una "ventana" apenas visible
    img.save(buf, format="PNG")
    assert post(api, buf.getvalue(), name="d.png", ctype="image/png").status_code == 200
    sent = Image.open(io.BytesIO(fake.calls[0][0])).convert("L")
    assert sent.getextrema()[1] > 200


@pytest.mark.parametrize(
    "payload,status,code",
    [
        (b"not an image at all", 415, "unsupported_format"),
        (b"\x00\x00\x00\x18ftypheic" + b"\x00" * 200, 415, "unsupported_format"),  # HEIC de iPhone
        (jpeg(size=(120, 120)), 400, "image_too_small"),
        (jpeg(size=(3000, 600)), 400, "bad_aspect_ratio"),
    ],
)
def test_bad_images_are_rejected_without_calling_model(api, fake, payload, status, code):
    r = post(api, payload)
    assert r.status_code == status and r.json()["error"] == code
    assert not fake.calls


def test_gif_is_rejected(api, fake):
    buf = io.BytesIO()
    Image.new("RGB", (400, 400)).save(buf, format="GIF")
    r = post(api, buf.getvalue(), name="a.gif", ctype="image/gif")
    assert r.status_code == 415


def test_truncated_jpeg_is_rejected(api, fake):
    assert post(api, jpeg()[:500]).status_code == 415


def test_upload_size_limit(api, fake, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    r = post(api, b"\xff\xd8" + b"0" * (1024 * 1024 + 10))
    assert r.status_code == 413 and r.json()["error"] == "image_too_large"


@pytest.mark.parametrize("style,code", [("", "style_required"), ("  a ", "style_required"), ("x" * 301, "style_too_long")])
def test_style_validation(api, fake, style, code):
    r = post(api, jpeg(), style=style)
    assert r.status_code in (400, 422)
    if r.status_code == 400:
        assert r.json()["error"] == code


@pytest.mark.parametrize(
    "error,status,code",
    [
        (http_error(402), 503, "quota_exhausted"),
        (http_error(429), 429, "provider_rate_limited"),
        (http_error(503), 503, "model_loading"),
        (http_error(401), 503, "not_configured"),
        (http_error(404), 502, "model_unsupported"),
        (http_error(500), 502, "upstream_error"),
        (InferenceTimeoutError("timeout"), 504, "timeout"),
        (ValueError("Model not supported by provider"), 502, "model_unsupported"),
        (RuntimeError("boom"), 502, "upstream_error"),
    ],
)
def test_provider_failures_become_clear_errors(api, fake, error, status, code):
    fake.error = error
    r = post(api, jpeg())
    assert r.status_code == status
    assert r.json()["error"] == code
    assert "hf_test" not in r.text


def test_rate_limit_per_client(api, fake, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "2")
    assert post(api, jpeg()).status_code == 200
    assert post(api, jpeg()).status_code == 200
    r = post(api, jpeg())
    assert r.status_code == 429 and r.json()["error"] == "rate_limited"
    assert int(r.headers["retry-after"]) > 0


def test_concurrency_limit(api, fake, monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENT_GENERATIONS", "1")
    service._active = 1
    r = post(api, jpeg())
    assert r.status_code == 503 and r.json()["error"] == "busy"


def test_slot_is_released_after_failure(api, fake):
    fake.error = http_error(500)
    post(api, jpeg())
    assert service._active == 0


def test_cors_only_for_allowed_origin(api, fake):
    ok = api.options("/api/renovate", headers={"Origin": "https://homeai.juancopado.chatgpt.site", "Access-Control-Request-Method": "POST"})
    bad = api.options("/api/renovate", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "https://homeai.juancopado.chatgpt.site"
    assert "access-control-allow-origin" not in bad.headers


def test_oversized_body_rejected_before_parsing(api, fake, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    body = b"x" * (2 * 1024 * 1024)
    r = api.post("/api/renovate", content=body, headers={"Content-Type": "multipart/form-data; boundary=zz", "Content-Length": str(len(body))})
    assert r.status_code == 413 and r.json()["error"] == "image_too_large"
    assert not fake.calls


def test_upload_never_spools_to_disk(api, fake, monkeypatch):
    import tempfile

    def no_disk(*a, **k):
        raise AssertionError("la foto se ha escrito en un archivo temporal")

    monkeypatch.setattr(tempfile, "TemporaryFile", no_disk)
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", no_disk)
    big = jpeg(size=(3000, 2250), color=(120, 110, 100))
    noisy = big + b"\x00" * (3 * 1024 * 1024)  # >1 MB: por defecto Starlette la volcaría a disco
    r = post(api, noisy)
    assert r.status_code == 200
