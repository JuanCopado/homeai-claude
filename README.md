# HomeAI — diseño y planificación integral de reforma

Web app independiente para diseñar y planificar una reforma. El proyecto inicia vacío para que las superficies y el presupuesto siempre correspondan a la vivienda real; el antiguo plano Tipo A era una muestra y ya no se precarga.

## Ejecutar localmente

1. Ejecuta `python3 -m http.server 8000` en esta carpeta.
2. Abre `http://localhost:8000`.
3. En Safari o Chrome, usa **Añadir a pantalla de inicio / Instalar** para abrirla como app.

La app funciona en móvil y escritorio. Guarda datos en el navegador de este dispositivo; no usa cuentas ni un servidor de almacenamiento. La única excepción es **Visualiza tu reforma con IA** (ver abajo): solo si la activas y das tu consentimiento, envía una copia reducida y sin datos de ubicación de la foto a un servicio de IA externo.

## Flujo de trabajo

- Importa un plano en PNG o JPG y calibra la escala en píxeles por metro.
- Usa **Leer con IA** para hacer OCR neuronal en español de nombres y medidas. En el primer uso, el navegador descarga Tesseract.js y los datos de idioma; la imagen se procesa en el dispositivo y no se envía al servicio HomeAI.
- Revisa y corrige dimensiones, agrega estancias y usa la herramienta **Editar muros** para trazar o quitar líneas.
- Genera una maqueta 3D conceptual a partir de líneas vectorizadas y una altura de pared editable. Orbita y acerca el modelo; exporta geometría OBJ y materiales MTL.
- Guarda paletas y materiales por estancia, añade cotizaciones, cantidades, precios y tareas, organiza archivos y exporta un dossier imprimible, presupuesto CSV, acabados CSV o copia de seguridad JSON.

## Alcance

La lectura de etiquetas usa un modelo de OCR. La reconstrucción 3D extruye líneas detectadas en la imagen; no usa un modelo generativo de arquitectura ni resuelve automáticamente habitaciones con precisión BIM. La escala y las paredes requieren revisión. La maqueta y las cantidades son orientativas, no un levantamiento ni un presupuesto contractual. Comprueba los datos con el plano y las medidas reales antes de tomar decisiones de obra.

## Visualiza tu reforma con IA (experimental)

En la vista Diseño: sube una foto de la estancia, elige un estilo (o descríbelo) y compara el antes y el después con un deslizador. Puedes guardar el resultado en Archivos o descartarlo.

Puedes cambiar **solo algunas zonas**: HomeAI detecta pared, suelo, techo y mobiliario; tócalas en la foto (una o varias), corrige con el pincel si hace falta y verás en verde exactamente qué se va a modificar. El resto de la foto se queda como está. O elige «Toda la foto».

Al subir la foto, HomeAI intenta reconocer el **estilo actual** de la estancia y lo muestra sobre la foto («Parece: Rústico»); puedes cambiarlo si no estás de acuerdo. A partir de él marca como *sugeridos* algunos estilos de reforma que suelen encajar, sin elegir por ti. Si la foto no deja claro el estilo (habitación vacía, exterior, mezcla de estilos), no afirma ninguno.

Cada visualización genera **2 versiones a la vez** y HomeAI muestra la mejor, descartando las que salen borrosas, deformadas o casi sin cambios. Si quieres, puedes ver la otra versión y quedarte con ella.

- **Sale del dispositivo**, a diferencia del resto de HomeAI: la foto se reduce a 1024 px y se re-codifica sin EXIF/GPS en el navegador, y se envía, con tu consentimiento explícito, al servicio de HomeAI (`server/`) y de ahí a Hugging Face. No se guarda en ningún servidor; el resultado solo se guarda en este navegador si pulsas «Guardar».
- Es una orientación visual: el modelo intenta conservar paredes, ventanas y distribución, pero puede cambiar detalles o inventar objetos.
- Está desactivada hasta que se configura la URL del servicio en `index.html`. Despliegue, límites y privacidad: `server/README.md`.

## Estudio fotográfico y alternativas (v13)

- Simulación local sobre fotografía: carga JPG, PNG o WebP (máximo 20 MB), marca polígonos de pared o suelo y aplica colores. Conserva la foto original; no genera muebles ni reconstruye geometría. Exportación PNG sin guías.
- Fotografías y superficies se guardan por estancia en IndexedDB. No se incluyen en la copia JSON; descarga los PNG por separado.
- 12 paletas coordinadas, colores personalizados HEX, filtros por familia y búsqueda sin distinción de tildes.
- Alternativas con nombre, recuperación y comparación por estancia. La copia JSON incluye las alternativas.
- Preparar compras crea partidas editables desde diseños guardados, sin duplicarlas ni inventar precios. Solo utiliza áreas de suelo confirmadas; las demás cantidades se completan manualmente.
- Desarrollo: npm install y npm run dev. Publicación estática: npm run build.

## V14 — ambientes, estancias y obra

- Galería filtrable de cuatro ambientes de referencia con imágenes originales, acabados y notas de revisión. Al aplicar una referencia, se puede crear una estancia tipada o usar una existente; las alternativas y diseños guardados se conservan.
- El paso de baño solo aparece para baños. Cocina, dormitorio, salón, comedor, terraza y baño ofrecen elecciones propias guardadas en la ficha de estancia.
- La lista de obra sugiere siete comprobaciones por estancia, con revisión adicional de impermeabilización e instalaciones de baño. Las tareas se pueden editar en Plan de obra.
- Descarga una ficha HTML imprimible por estancia con acabados, medidas confirmadas y recomendaciones de revisión.
- Los ambientes son referencias visuales, no reproducciones de tu vivienda ni planos ejecutivos. El estudio fotográfico es una simulación manual de color/material.

## V16 — orientación, favoritos y decisiones por estancia

- Guía de estilo opcional: estancia, ambiente deseado y prioridad; tres combinaciones curadas aplicables al borrador. No se presenta como generación IA.
- Favoritos buscables para estilos, materiales, colores, paletas y elecciones de equipamiento; almacenamiento local independiente.
- Siete ambientes ilustrativos, con tres imágenes nuevas: art déco, baño mineral y dormitorio juvenil.
- 73 decisiones específicas distribuidas entre seis tipos de estancia, con grupos desplegables y exportación coherente.
- Comparación de alternativas incorpora detalles específicos de estancia. Mejoras de legibilidad, controles táctiles y navegación de diálogos por teclado.
- Correcciones de selección de estancia, ruta foto/concepto, guardado inicial, copia de detalles y vaciado del guardado pendiente al salir.
- Caché v16 preparada para actualizar recursos. Una actualización no elimina proyectos ni fotografías locales.
- Validación: `node tests/design-state.test.mjs`, comprobaciones de sintaxis y build. La revisión visual v16 quedó bloqueada por el límite de uso del sistema de aprobación del navegador; no consta como superada.
