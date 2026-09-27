# Pipeline de generación con Qwen-Image-Edit (2026-09-27)

Corrección del pipeline tras la medición del filtro de calidad: SDXL ya no se
sirve, el coste limitaba las variantes y el puntuador no detectaba variantes
casi idénticas al original. Decisiones de Juan (no se reabren): Qwen-Image-Edit
sustituye a SDXL (FLUX Kontext descartado por licencia no comercial), máximo 2
variantes con filtro de similitud ANTES del puntuador, medición de QA en Colab,
y una prueba pequeña (2-3 llamadas) contra la API real para el coste.

## Qué cambió (ai-engineer)

- **Modelo:** `Qwen/Qwen-Image-Edit` por defecto (Apache-2.0).
- **Prompts** (`server/pipeline.py`): Qwen-Image-Edit es un modelo de edición por
  instrucciones. Qwen2.5-VL lee el texto mirando la foto (semántica) y el VAE
  conserva la apariencia. Por eso:
  - el prompt es una instrucción («Redecorate this room in this style: … Keep
    the same room and the same camera angle…»), no una lista de etiquetas;
  - no existe `strength`: la intensidad de la interfaz se traduce a la
    instrucción (retoque / cambiar muebles y acabados / rediseño completo);
  - la guía es `true_cfg_scale` con prompt negativo (4, 30 pasos).
  Con un img2img clásico en `HF_MODEL` se mantiene el prompt anterior con `strength`.
- **Variantes:** máximo 2, tope fijo en el código.
- **Filtro de similitud antes del puntuador:** similitud coseno CLIP con el
  original (en el recorte de la zona si hay zonas). Por encima de 0,89 la
  variante se descarta y **se regenera una vez**; solo las que pasan llegan al
  puntuador estético. Las de calidad baja no se regeneran (coste). Se eligió
  CLIP y no pHash porque la medición anterior mostró que una variante solo más
  luminosa cambia mucho los píxeles y un hash, mientras que CLIP sí la
  reconoce como la misma foto.
- **Backend configurable:** `GEN_BACKEND=api` (por defecto) o `diffusers`
  (`server/local_qwen.py`, `QwenImageEditPipeline` en GPU propia, 4 bits
  opcional, LoRA Lightning opcional).
- **Notebook de Colab** (`server/validation/colab/qwen_edit_colab.ipynb`),
  generado desde el código del servidor para que QA mida exactamente lo que va
  a producción. CI comprueba que está sincronizado y lo ejecuta de punta a
  punta con un Qwen diminuto en CPU.
- **Prueba de coste:** `server/validation/api_cost_probe.py` + workflow manual
  `api-cost-probe.yml` (tope fijo de 3 llamadas; se para en el primer 402).

## Revisión del plan y el presupuesto (architect)

**Esto es una estimación con tarifas públicas.** El coste real sale de la prueba
de 2-3 llamadas, que está preparada pero todavía no se ha ejecutado.

Tarifas de referencia (septiembre de 2026):
- fal-ai (el proveedor que sirve Qwen-Image-Edit en HF): 0,03 $ por megapíxel;
- HF repercute la tarifa del proveedor sin recargo;
- plan gratuito de HF: 0,10 $ de crédito al mes y, al agotarse, se corta;
- PRO: 9 $/mes con 2 $ de crédito incluidos, y después pago por uso.

| | SDXL (antes, 3 variantes) | Qwen-Image-Edit (ahora, 2 variantes) |
|---|---|---|
| Llamadas por petición | 3 (+3 si se reintentaba todo) | 2 (+1 por cada una casi idéntica) |
| Coste por petición | no se sirve | **~0,06 $** (peor caso ~0,12 $) |
| Peticiones con el crédito gratuito | — | ~1 al mes |
| Peticiones con los 2 $ de PRO | — | ~33 al mes |

Conclusiones:

1. **Hay que cambiar de plan para producción.** Con el plan gratuito (0,10 $/mes)
   cabe una sola petición al mes. Para abrir la función hace falta **HF PRO**
   (9 $/mes). Por encima de ~33 peticiones al mes, se pagan ~0,06 $ por petición:

   | Peticiones/mes | Coste aproximado |
   |---|---|
   | 100 | 9 $ + 4 $ |
   | 500 | 9 $ + 28 $ |
   | 1000 | 9 $ + 58 $ |
2. **Hace falta un tope de gasto global antes de abrirla al público.** El
   límite actual es por IP (10 generaciones/hora). Con pago por uso, alguien
   que cambie de IP podría generar un gasto sin techo. Recomendación: un tope
   diario global de generaciones en el servidor. Es un cambio pequeño y está
   pendiente de decisión.
3. **GPU propia (backend diffusers): todavía no compensa.**
   - Precios de las Inference Endpoints de HF:
     - L4 de 24 GB (vale en 4 bits): 0,80 $/h;
     - A100 de 80 GB (vale sin cuantizar): 2,50 $/h.
   - Con una L4 haría falta sostener unas 13 peticiones por hora para igualar a
     la API.
   - Además, el arranque en frío es de varios minutos, porque hay que cargar
     ~58 GB de pesos.
   - Revisar cuando el tráfico sea estable o cuando Colab mida el tiempo real
     por imagen.
4. **El servicio actual (Space CPU gratuito) no cambia.** El filtro de similitud
   usa el CLIP ya cargado para la detección de estilo (+1-2 s de CPU por
   variante).

## Estado de la validación

- **Hecho:**
  - 92 tests del servidor;
  - la interfaz, en el navegador, contra el servidor real con modelo simulado,
    confirma que:
    - llega la instrucción de Qwen sin `strength`;
    - una petición hace 2 llamadas, más 2 regeneraciones cuando las dos salen
      casi idénticas;
    - no hay errores de consola ni scroll horizontal a 390 y 1440 px.
  - El notebook se ejecuta en CI con un Qwen diminuto.
- **Pendiente (requiere a Juan):**
  1. **Ejecutar el notebook en Colab** (GPU T4 gratuita; instrucciones dentro) y
     subir `qa_qwen.zip`. De ahí salen:
     - la estabilidad;
     - la tasa de descarte del filtro de similitud;
     - la comparación de calidad con SDXL, ejecutada en la misma T4 porque
       SDXL nunca llegó a generarse por la API en este proyecto;
     - la calibración real de `SIMILARITY_MAX`.
  2. **Lanzar `api-cost-probe.yml` cuando se renueve el crédito** (2 llamadas ≈
     0,06 $, cabe en los 0,10 $ gratuitos), y mirar el cargo exacto en
     https://huggingface.co/settings/billing.
- **Riesgos del notebook, sin verificar con los pesos reales** (este entorno no
  tiene GPU):
  - el primer intento en la T4 puede quedarse corto de memoria;
  - la LoRA Lightning sobre el modelo en 4 bits puede no cargar. En ese caso,
    el notebook sigue sin ella, a 30 pasos y más lento, y lo anota en el
    informe;
  - fp16 podría dar imágenes negras. El informe lo detecta; se corrige cambiando
    `QWEN_DTYPE`.
