"""Comprueba el código de PRODUCCIÓN de la detección de estilo
(server/style.py + POST /api/style) con CLIP large/14 real, sobre las fotos
de Wikimedia de results_style/ ya revisadas a mano (se recargan por título).

Resultado esperado según la validación: estilo correcto cuando se sugiere, y
ninguna sugerencia en exteriores / habitaciones vacías / dudas.
Salida: results_style_server/report.md. Se ejecuta en GitHub Actions.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("STYLE_RATE_LIMIT_PER_HOUR", "1000")

from fastapi.testclient import TestClient  # noqa: E402

import app as service  # noqa: E402
from compare_models import fetch_by_title  # noqa: E402

OUT = HERE / "results_style_server"
# Revisión manual de results_style/ (ver CURRENT_STATE.md): qué debería pasar.
EXPECTED = {
    "01": "rustico", "02": "rustico", "03": "no", "04": "no", "05": "no", "06": "no",
    "07": "minimalista", "08": "no", "09": "moderno", "10": "moderno", "11": "no", "12": "no",
}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    api = TestClient(service.app)
    summary = json.loads((HERE / "results_style" / "summary.json").read_text(encoding="utf-8"))
    rows, bad = [], 0
    for s in summary:
        n = f"{s['n']:02d}"
        if n not in EXPECTED or not s["title"].startswith("File:"):
            continue
        img = fetch_by_title(s["title"]).convert("RGB")
        img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92)
        r = api.post("/api/style", files={"image": ("f.jpg", buf.getvalue(), "image/jpeg")})
        assert r.status_code == 200, r.text
        body = r.json()
        got = body["style"] if body["suggest"] else "no"
        exp = EXPECTED[n]
        # "no" esperado: lo único incorrecto sería sugerir algo. Estilo esperado:
        # vale acertarlo o no sugerir (el umbral puede callar), nunca otro estilo.
        ok = (got == "no") if exp == "no" else (got in (exp, "no"))
        bad += not ok
        rows.append(f"| {n} | {exp} | {got} | {body['confidence']} / +{body['margin']} | {body['reason'] or ''} | {'✅' if ok else '❌'} |")
    report = ["# Detección de estilo: código de producción con CLIP large/14 real", "",
              "| Foto | Esperado | Respuesta | Confianza / margen | Motivo si no sugiere | OK |",
              "|---|---|---|---|---|---|", *rows, "",
              f"Sugerencias incorrectas: {bad}."]
    (OUT / "report.md").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
