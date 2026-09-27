# Reconstrucción 3D de habitaciones a partir de fotos — investigación (2026-09-27)

Objetivo: elegir la herramienta para la **Fase 0 del recorrido virtual**
(foto(s) de una estancia → modelo 3D que se pueda girar en el navegador), solo
con opciones gratuitas / de código abierto **con licencia de uso comercial**.

Método: metadatos consultados en vivo (Hugging Face y GitHub) y pruebas reales
de las 3 candidatas más prometedoras con fotos reales de pisos, en la CPU de un
runner de GitHub Actions (4 núcleos, sin GPU). Código en
`server/validation/r3d/`, workflow `.github/workflows/research-3d.yml`,
resultados completos (tabla, vistas girada/cenital y nubes `.glb`) en
`server/validation/results_3d/report.md`.

## Tabla comparativa

| Herramienta | Entrada | Licencia (pesos / código) | ¿Comercial? | Requisitos | Salida / visor web | Calidad observada |
|---|---|---|---|---|---|---|
| **MoGe-2** (ViT-L, Microsoft) | 1 foto | MIT / MIT | ✅ | CPU: **28 s** por foto (fp32; fp16 falla en CPU). ~1,3 GB de pesos | Nube de puntos métrica + cámara estimada → GLB → three.js | **La mejor con 1 foto.** Paredes rectas, suelo plano, muebles con su forma al girar; escala real (pared del fondo ~4 m en el salón, ~2,5 m en la cocina) |
| **MapAnything** (variante Apache, Meta) | 1 o varias fotos | Apache-2.0 / Apache-2.0 | ✅ | CPU: 13 s (1 foto), **75 s (4 fotos)** | Nube métrica multivista → GLB → three.js | Une 4 fotos del baño en una escena coherente; con 1 foto, correcta pero más ruidosa que MoGe-2. Espejos y mamparas crean puntos fantasma |
| **Depth Anything V2 Small** | 1 foto | Apache-2.0 / Apache-2.0 | ✅ | CPU: **1–2 s** | Solo profundidad **relativa** (sin cámara ni escala; FOV supuesto) | Bien desde el ángulo original; al girar, suelo y paredes se curvan. Sirve para efecto parallax, no para un recorrido |
| VGGT-1B-Commercial (Meta) | varias fotos | licencia propia comercial, acceso restringido | ✅ (con aceptación) | GPU recomendada | Nube + cámaras | **No probado:** repo restringido (HTTP 403). Hay que solicitar acceso |
| Depth Pro (Apple) | 1 foto | apple-amlr | ❌ solo investigación | — | — | Descartado por licencia |
| MASt3R / DUSt3R | varias fotos | CC BY-NC-SA | ❌ | — | — | Descartado por licencia |
| SpatialLM | nube → planta | CC BY-NC 4.0 | ❌ | — | — | Descartado por licencia |
| InSpace | 1 panorámica 360° | MIT | ✅ | GPU | Malla | Requiere panorámica 360°, no fotos normales; a considerar más adelante |
| gsplat (Gaussian Splatting) | vídeo / 30+ fotos | Apache-2.0 | ✅ | **GPU obligatoria**, minutos por escena | `.ply`/`.splat` → SuperSplat (MIT) | La mejor calidad visual posible, pero fuera del alcance de un servicio CPU gratuito |
| OpenSplat | vídeo / fotos | AGPL-3.0 | ⚠️ obliga a publicar el código del servicio | GPU o CPU muy lenta | `.ply` | Descartado por la AGPL |

## Recomendación

- **Fase 0: MoGe-2 con una sola foto.** Es la única que da geometría
  coherente y en metros desde una foto, con licencia MIT, y cabe en el
  servicio actual (Hugging Face Space CPU): ~28 s por foto, del orden de una
  generación de reforma. Salida GLB (nube de puntos coloreada) visible en el
  navegador con three.js y `GLTFLoader`, sin plugins.
- **Fase 1: MapAnything-Apache** para unir varias fotos de la misma estancia
  (75 s para 4 fotos en CPU). Hay que filtrar espejos/cristales (p. ej. con la
  segmentación que ya tenemos) para quitar los puntos fantasma.
- **Más adelante (con GPU):** Gaussian Splatting con gsplat + visor SuperSplat
  para un recorrido fotorrealista desde un vídeo.
- **Visor:** three.js (MIT). Es lo que usa la página de resultados; en HomeAI
  se cargaría bajo demanda solo en la vista del recorrido.

## Implicaciones para HomeAI

- Nuevo endpoint `/api/reconstruct` en `server/` (misma política de
  privacidad: nada en disco, sin registros de fotos). La nube de 500–800 k
  puntos pesa 7–10 MB en GLB; conviene reducirla a ~150 k puntos (~2 MB)
  antes de enviarla.
- Añadir three.js al frontend supone una dependencia nueva (~600 KB): revisión
  de Architect y Security antes de integrarla.
- La profundidad métrica de MoGe-2 también sirve para medidas aproximadas
  (ancho de pared, altura) en otras funciones.

## Pendiente

- **VGGT-1B-Commercial:** Juan tiene que solicitar acceso en
  https://huggingface.co/facebook/VGGT-1B-Commercial con la cuenta del
  `HF_TOKEN`; después se relanza `research-3d.yml` y se compara con
  MapAnything.
- Probar MoGe-2 con más casos difíciles (contraluz, habitación vacía, espejos).

Fotos de prueba: Wikimedia Commons (CC0 y CC BY-SA 4.0), atribución completa
en `server/validation/results_3d/report.md`.
