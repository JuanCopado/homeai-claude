# Calibración del puntuador de calidad

## 1. Fallos simulados (nota del fallo < nota del original)

| Foto | Original | borrosa | ruido | jpeg | deformada | quemada |
|---|---|---|---|---|---|---|
| 01 | 0.801 | 0.631 ✅ | 0.216 ✅ | 0.346 ✅ | 0.364 ✅ | 0.747 ✅ |
| 02 | 0.76 | 0.623 ✅ | 0.617 ✅ | 0.073 ✅ | 0.205 ✅ | 0.493 ✅ |
| 03 | 0.754 | 0.63 ✅ | 0.423 ✅ | 0.449 ✅ | 0.245 ✅ | 0.732 ✅ |
| 04 | 0.733 | 0.599 ✅ | 0.451 ✅ | 0.123 ✅ | 0.208 ✅ | 0.341 ✅ |
| 05 | 0.75 | 0.634 ✅ | 0.602 ✅ | 0.239 ✅ | 0.274 ✅ | 0.211 ✅ |
| 06 | 0.779 | 0.324 ✅ | 0.434 ✅ | 0.145 ✅ | 0.168 ✅ | 0.372 ✅ |

Fallos con nota menor que su original: **30/30**; diferencia media 0.366.

## 2. Variantes reales (FLUX Kontext, «estilo nórdico»)

| Variante | A ojo | score | similitud CLIP con el original |
|---|---|---|---|
| v1 | casi sin cambios | 0.706 | 0.8985 |
| v2 | reforma nórdica completa | 0.784 | 0.7909 |
| v3 | cambio intermedio | 0.74 | 0.8758 |

Referencia: original contra sí mismo, similitud = 1.0.

## Umbrales elegidos (server/app.py)

- `QUALITY_MIN_SCORE = 0.5`: en la primera calibración descartó 21/30 fallos graves y ninguna
  variante real (0.71–0.78). Los fallos leves (algo borrosa/quemada) no se descartan pero
  quedan por debajo en la clasificación.
- `SIMILARITY_MAX = 0.89` (antes QUALITY_MIN_CHANGE = 0.11): entre «sin cambios» (~0.90)
  e «intermedio» (~0.88). Se aplica ANTES del puntuador y regenera las casi idénticas.
  **Provisional: 1 sola foto real.** Recalibrar con la medición completa cuando haya crédito,
  también en modo zonas (ahí el cambio se mide en el recorte de la zona).