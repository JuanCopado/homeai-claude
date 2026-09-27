"""Detección de estilo: reglas de decisión (umbral, margen, etiquetas de
no-sugerir) y endpoint. CLIP se sustituye por un doble que devuelve las
probabilidades a probar; la calidad del modelo real se validó aparte
(server/validation/validate_style.py)."""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app as service
import style


def probs(**kw):
    """Probabilidades para las claves de style.KEYS; el resto se reparte."""
    rest = (1 - sum(kw.values())) / (len(style.KEYS) - len(kw))
    return [kw.get(k, rest) for k in style.KEYS]


def photo():
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (180, 170, 160)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "100")
    service._hits.clear()
    service._active = service._seg_active = 0
    return TestClient(service.app)


def use(monkeypatch, p):
    monkeypatch.setattr(style, "load_classifier", lambda: (lambda img: p))


# --- reglas ----------------------------------------------------------------------

def test_clear_style_is_suggested():
    r = style.decide(probs(rustico=0.8, moderno=0.1))
    assert r["suggest"] and r["style"] == "rustico" and r["label"] == "Rústico"
    assert r["top"][0]["style"] == "rustico" and len(r["top"]) == 3


@pytest.mark.parametrize("p1,p2", [(0.45, 0.1), (0.5, 0.35), (0.55, 0.4)])
def test_doubtful_model_does_not_suggest(p1, p2):
    r = style.decide(probs(industrial=p1, moderno=p2))
    assert not r["suggest"] and r["style"] is None
    assert "estilo claro" in r["reason"]


@pytest.mark.parametrize("sink,text", [("vacia", "vacía"), ("objeto", "de cerca"), ("exterior", "exterior")])
def test_sink_labels_never_suggest_a_style(sink, text):
    # Aunque el sumidero gane con mucha seguridad, no se sugiere estilo.
    r = style.decide(probs(**{sink: 0.97}))
    assert not r["suggest"] and r["style"] is None and text in r["reason"]
    assert all(t["style"] in style.STYLES for t in r["top"])  # el top solo lista estilos


def test_thresholds_match_validation():
    assert (style.MIN_PROB, style.MIN_MARGIN) == (0.5, 0.2)
    assert style.decide(probs(clasico=0.5, moderno=0.3))["suggest"]  # justo en el límite


# --- /api/style ------------------------------------------------------------------

def test_endpoint_returns_detection_without_token(api, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)  # no gasta crédito de HF
    use(monkeypatch, probs(escandinavo=0.7, minimalista=0.1))
    r = api.post("/api/style", files={"image": ("a.jpg", photo(), "image/jpeg")})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["style"] == "escandinavo" and body["suggest"] is True
    assert 0 < body["confidence"] <= 1 and body["margin"] > 0.2


def test_endpoint_empty_room(api, monkeypatch):
    use(monkeypatch, probs(vacia=0.95))
    body = api.post("/api/style", files={"image": ("a.jpg", photo(), "image/jpeg")}).json()
    assert body["suggest"] is False and body["style"] is None and body["reason"]


def test_endpoint_rejects_bad_images(api, monkeypatch):
    use(monkeypatch, probs(moderno=0.9))
    r = api.post("/api/style", files={"image": ("a.gif", b"GIF89a" + b"\x00" * 50, "image/gif")})
    assert r.status_code == 415


def test_endpoint_model_failure(api, monkeypatch):
    def broken():
        raise RuntimeError("sin red para descargar el modelo")

    monkeypatch.setattr(style, "load_classifier", broken)
    r = api.post("/api/style", files={"image": ("a.jpg", photo(), "image/jpeg")})
    assert r.status_code == 503 and r.json()["error"] == "style_unavailable"
    assert service._seg_active == 0


def test_endpoint_rate_limit(api, monkeypatch):
    monkeypatch.setenv("STYLE_RATE_LIMIT_PER_HOUR", "1")
    use(monkeypatch, probs(moderno=0.9))
    assert api.post("/api/style", files={"image": ("a.jpg", photo(), "image/jpeg")}).status_code == 200
    assert api.post("/api/style", files={"image": ("a.jpg", photo(), "image/jpeg")}).status_code == 429
