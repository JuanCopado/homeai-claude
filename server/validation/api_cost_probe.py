"""Prueba PEQUEÑA y deliberada contra la Inference API real para conocer el
coste por petición de Qwen-Image-Edit en producción (Colab es gratis y no
sirve para esto).

- Como mucho 3 llamadas (PROBE_CALLS, por defecto 2 = una petición real de
  la interfaz). Tope fijo en el código: no se puede subir por configuración.
- Usa el código de producción (app.generate con la configuración por
  defecto: Qwen/Qwen-Image-Edit, proveedor "auto") y una foto real.
- Se para en el primer 402 (crédito agotado) sin reintentar.
- Coste: HF no expone el saldo por API de forma documentada. Se intenta leer
  el uso antes y después (si responde, se calcula la diferencia) y, en todo
  caso, se estima con la tarifa pública del proveedor por megapíxel. Del uso
  solo se guardan el código HTTP y los nombres de campo (el informe se sube al
  repositorio y no debe llevar datos de la cuenta). El dato
  exacto queda en https://huggingface.co/settings/billing (Juan).

Necesita el secreto HF_TOKEN; se lanza SOLO a mano (workflow api-cost-probe.yml).
Salida: results_api_cost/report.md
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

OUT = HERE / "results_api_cost"
MAX_CALLS = 3
PHOTO = "File:Apartment Living Room 4 2018-09-28.jpg"
STYLE = "estilo nórdico escandinavo, paredes blancas, madera clara, textiles de lino, plantas"
# Tarifas públicas por megapíxel de salida (septiembre de 2026). Solo para
# estimar si el uso real no se puede leer.
PRICE_PER_MP = {"fal-ai": 0.03}
USAGE_URLS = ["https://huggingface.co/api/settings/billing/usage", "https://huggingface.co/api/billing/usage"]


def read_usage(token: str):
    """Intento best-effort de leer el uso facturado. Nunca imprime el token."""
    import requests

    for url in USAGE_URLS:
        try:
            r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        except Exception as exc:  # noqa: BLE001
            yield url, f"error {type(exc).__name__}", None
            continue
        body = None
        if r.ok and "json" in r.headers.get("content-type", ""):
            body = r.json()
        yield url, r.status_code, body


def main() -> int:
    OUT.mkdir(exist_ok=True)
    token = os.environ.get("HF_TOKEN", "").strip()
    report = ["# Coste real por petición: Qwen-Image-Edit por la Inference API", ""]
    if not token:
        report.append("**No se ejecutó: falta el secreto `HF_TOKEN`.**")
        (OUT / "report.md").write_text("\n".join(report), encoding="utf-8")
        print(report[-1])
        return 0
    calls = min(MAX_CALLS, max(1, int(os.environ.get("PROBE_CALLS", "2"))))

    import app as service
    from compare_models import fetch_by_title
    from huggingface_hub import HfApi

    cfg = service.settings()
    mapping = HfApi(token=token).model_info(cfg["model"], expand=["inferenceProviderMapping"]).inference_provider_mapping or []
    provs = [f"{m.provider} ({m.status})" for m in mapping if getattr(m, "task", None) == "image-to-image"]
    first = next((m.provider for m in mapping if getattr(m, "task", None) == "image-to-image" and m.status == "live"), None)
    before = list(read_usage(token))

    buf = io.BytesIO()
    fetch_by_title(PHOTO).convert("RGB").save(buf, format="JPEG", quality=92)
    img = service.preprocess(buf.getvalue(), cfg["max_side"])
    prompt = service.build_prompt(STYLE, [], 0.55, service.is_edit_model(cfg["model"]))
    rows, stopped = [], None
    for i in range(calls):
        t0 = time.perf_counter()
        try:
            out = service.generate(img, prompt, 0.55, cfg)
            rows.append({"call": i + 1, "ok": True, "seconds": round(time.perf_counter() - t0, 1)})
            out.save(OUT / f"call_{i + 1}.jpg", quality=85)
        except service.ApiError as exc:
            rows.append({"call": i + 1, "ok": False, "error": exc.code, "seconds": round(time.perf_counter() - t0, 1)})
            if exc.code in ("quota_exhausted", "not_configured", "model_unsupported"):
                stopped = exc.code
                break
    time.sleep(20)  # el uso tarda un poco en reflejarse
    after = list(read_usage(token))

    # El proveedor trabaja a ~1 MP (Qwen redimensiona a 1024×1024 de área).
    mp = 1.0
    ok = sum(1 for r in rows if r["ok"])
    price = PRICE_PER_MP.get(first or "", None)
    report += [f"Modelo `{cfg['model']}`, proveedor `{cfg['provider']}` → servido por: {', '.join(provs) or '—'}.",
               f"Primer proveedor «live» (el que usa `auto`): **{first or '—'}**. Foto {img.width}×{img.height} "
               f"({img.width * img.height / 1e6:.2f} MP enviados; salida ~{mp:.1f} MP).", "",
               "| Llamada | Resultado | Segundos |", "|---|---|---|",
               *[f"| {r['call']} | {'✅' if r['ok'] else '❌ ' + r['error']} | {r['seconds']} |" for r in rows], ""]
    if stopped:
        report += [f"**Parada: `{stopped}`.** Si es `quota_exhausted`, el crédito aún no se ha renovado.", ""]
    report += ["## Coste", ""]
    if price is not None:
        report += [f"- Estimado con la tarifa pública de {first} ({price} $/MP): **{price * mp:.3f} $ por imagen**, "
                   f"**{2 * price * mp:.3f} $ por petición de 2 variantes** "
                   f"(hasta {4 * price * mp:.3f} $ si se regeneran las dos).",
                   f"- Esta prueba: {ok} imágenes ≈ {ok * price * mp:.3f} $."]
    report += ["- Uso leído de la API de facturación (best-effort):"]
    for (url, st_b, body_b), (_, st_a, body_a) in zip(before, after):
        report.append(f"  - `{url}`: HTTP {st_b} → {st_a}")
        if isinstance(body_a, dict):
            # Solo los nombres de los campos: la respuesta puede tener datos de
            # la cuenta y este informe se sube al repositorio.
            report.append(f"    campos: {', '.join(sorted(body_a))[:300]}")
    report += ["- **Dato exacto:** https://huggingface.co/settings/billing → uso de Inference Providers del día.", "",
               *[f"![llamada {r['call']}](call_{r['call']}.jpg)" for r in rows if r["ok"]]]
    (OUT / "report.md").write_text("\n".join(report), encoding="utf-8")
    (OUT / "data.json").write_text(json.dumps({"rows": rows, "providers": provs, "first": first}, indent=1),
                                   encoding="utf-8")
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
