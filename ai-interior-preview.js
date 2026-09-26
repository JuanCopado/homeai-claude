/* Generador de imágenes de inspiración con IA (punto 4 del encargo de Juan:
   IA generativa de interiores), usando @aislamov/diffusers.js (Stable
   Diffusion 2.1 base, ONNX + WebGPU) cargado bajo demanda desde CDN — mismo
   patrón que loadTesseract() en app.js y que ai-orchestrator.js.

   ALCANCE HONESTO DE ESTA PRIMERA VERSIÓN: genera una imagen de referencia
   a partir de una descripción de estilo (texto→imagen). NO parte de la foto
   real de la estancia del usuario ni la modifica (eso sería imagen→imagen o
   ControlNet condicionado a la foto, cuya forma exacta de API no se pudo
   verificar de forma fiable en esta sesión — ver CURRENT_STATE.md). Por
   eso la imagen resultante se etiqueta siempre como "de inspiración, no es
   tu estancia real": es la CAPA GENERATIVA en su forma más simple posible,
   completamente desconectada de project.rooms/geometry — cumple la regla de
   Juan ("la IA generativa nunca toca la geometría verificada") por
   construcción, no solo por buena intención, precisamente porque no la lee. */
(()=>{'use strict';
const MODEL_ID='aislamov/stable-diffusion-2-1-base-onnx';
const CDN_URL='https://cdn.jsdelivr.net/npm/@aislamov/diffusers.js@0.9.3/+esm';
let pipelinePromise=null;

function injectUI(){
  const designView=$('#view-design');
  const anchor=designView&&designView.querySelector('.saved-finishes');
  if(!designView||!anchor||$('#aiInteriorCard'))return;
  const card=document.createElement('article');
  card.className='card ai-interior-card';
  card.id='aiInteriorCard';
  card.innerHTML=`<div class="card-heading"><div><h2>Imagen de inspiración con IA (experimental)</h2><p>Describe un ambiente y genera una imagen de referencia. No es una foto de tu estancia real ni cambia tu diseño guardado — es solo inspiración visual.</p></div></div><div class="ai-orch-body"><textarea id="aiInteriorInput" class="ai-orch-input" rows="2" placeholder="Ej.: salón estilo japandi, tonos claros, suelo de madera natural, mucha luz"></textarea><div class="ai-orch-actions"><button type="button" class="btn btn-dark" id="aiInteriorRun">Generar imagen</button><span id="aiInteriorStatus" class="ai-orch-status" aria-live="polite"></span></div><div id="aiInteriorOutput" class="ai-interior-output" hidden><img id="aiInteriorImg" alt="Imagen de inspiración generada por IA"><small>Imagen generada por IA a partir de tu descripción — no es una foto de tu estancia real.</small></div></div><div class="info-strip"><span>ⓘ</span><p>La primera vez, este generador descarga un modelo de IA (varios GB) y lo ejecuta enteramente en tu navegador — nada se envía a ningún servidor. Necesita un navegador con soporte WebGPU y puede tardar varios minutos, sobre todo la primera vez. Es experimental: mejor en un ordenador con buena GPU que en un móvil.</p></div>`;
  anchor.after(card);
  $('#aiInteriorRun').onclick=runGeneration;
}

async function loadPipeline(onProgress){
  if(pipelinePromise)return pipelinePromise;
  if(!('gpu' in navigator))throw new Error('no-webgpu');
  pipelinePromise=(async()=>{
    const {DiffusionPipeline}=await import(/* webpackIgnore: true */ CDN_URL);
    return DiffusionPipeline.fromPretrained(MODEL_ID,{progressCallback:onProgress});
  })();
  try{return await pipelinePromise}catch(e){pipelinePromise=null;throw e}
}

/* La forma exacta del objeto que devuelve pipe.run() no se pudo verificar de
   forma fiable en esta sesión (documentación pública incompleta sobre este
   punto concreto) — en vez de adivinar una sola forma y arriesgarse a que
   falle en silencio o, peor, a mostrar algo incorrecto con confianza falsa,
   esta función prueba varias formas conocidas de librerías de difusión en
   navegador (helper toBlobURL/toDataURL, Blob, HTMLCanvasElement, o un
   tensor {data,width,height}) y devuelve null si ninguna encaja, para que
   quien la llama lo trate como un fallo honesto en vez de una imagen falsa. */
async function imageResultToUrl(image){
  if(!image)return null;
  try{
    if(typeof image.toBlobURL==='function')return await image.toBlobURL();
    if(typeof image.toDataURL==='function')return image.toDataURL();
    if(typeof Blob!=='undefined'&&image instanceof Blob)return URL.createObjectURL(image);
    if(typeof HTMLCanvasElement!=='undefined'&&image instanceof HTMLCanvasElement)return image.toDataURL();
    if(image.data&&image.width&&image.height){
      const canvas=document.createElement('canvas');
      canvas.width=image.width;canvas.height=image.height;
      const ctx=canvas.getContext('2d');
      const data=image.data instanceof Uint8ClampedArray?image.data:new Uint8ClampedArray(image.data);
      ctx.putImageData(new ImageData(data,image.width,image.height),0,0);
      return canvas.toDataURL();
    }
  }catch{return null}
  return null;
}

async function runGeneration(){
  const input=$('#aiInteriorInput').value.trim();
  if(!input){toast('Describe primero el ambiente que quieres generar.');return}
  const status=$('#aiInteriorStatus'),output=$('#aiInteriorOutput'),img=$('#aiInteriorImg'),btn=$('#aiInteriorRun');
  btn.disabled=true;output.hidden=true;status.textContent='Comprobando compatibilidad…';
  try{
    const pipe=await loadPipeline(p=>{status.textContent=p&&p.text?p.text:'Cargando modelo de IA…'});
    status.textContent='Generando imagen (puede tardar varios minutos)…';
    const images=await pipe.run({prompt:input,numInferenceSteps:20});
    const image=Array.isArray(images)?images[0]:images;
    const url=await imageResultToUrl(image);
    if(!url)throw new Error('formato-salida-desconocido');
    img.src=url;output.hidden=false;
    status.textContent='Listo. Recuerda: es una imagen de inspiración, no tu estancia real.';
  }catch(e){
    output.hidden=true;
    status.textContent=e&&e.message==='no-webgpu'
      ?'Tu navegador no soporta WebGPU, así que este generador no puede ejecutarse aquí. Prueba con un ordenador reciente con Chrome o Edge, o sigue con el catálogo y la guía de estilo.'
      :'No se pudo generar la imagen ahora (puede ser tu conexión, memoria del navegador, o que este modelo experimental no cargó). Puedes seguir usando el catálogo y la guía de estilo mientras tanto.';
  }finally{btn.disabled=false}
}

injectUI();
})();
