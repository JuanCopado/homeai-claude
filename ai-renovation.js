/* Visualización de reforma con IA (fase 1): el usuario sube una foto real de
   su estancia, describe un estilo, y un modelo img2img de Hugging Face la
   "redecora" manteniendo paredes, ventanas y disposición.

   A diferencia de ai-interior-preview.js (todo local, texto→imagen), esta
   función SÍ envía la foto fuera del dispositivo: al microservicio de
   server/ (que guarda el token de Hugging Face como secreto) y de ahí al
   proveedor de inferencia. Por eso:
   - no hace nada hasta que el usuario marca el consentimiento explícito;
   - reduce y re-codifica la foto en el navegador antes de enviarla (quita
     EXIF/GPS y limita a 1024 px);
   - el resultado solo se guarda si el usuario pulsa "Guardar en Archivos"
     (IndexedDB local, vía handleDocument() de app.js).

   La URL del servicio se configura en index.html
   (<meta name="homeai-renovation-endpoint">). Vacía = función desactivada.
   Para pruebas locales se puede sobrescribir con
   localStorage['homeai.renovationEndpoint']. */
(()=>{'use strict';
const MAX_SIDE=1024;
const CLIENT_TIMEOUT_MS=150000;
const ACCEPTED=['image/jpeg','image/png','image/webp'];
const STYLES=[
  ['Nórdico','estilo nórdico escandinavo, paredes blancas, madera clara, textiles de lino, plantas'],
  ['Japandi','estilo japandi, tonos arena y beige, madera natural, líneas limpias, minimalista y cálido'],
  ['Industrial','estilo industrial, ladrillo visto, metal negro, madera envejecida, lámparas colgantes'],
  ['Mediterráneo','estilo mediterráneo, paredes encaladas, terracota, azul, fibras naturales'],
  ['Minimalista','estilo minimalista moderno, blanco y gris claro, muebles bajos, sin objetos decorativos'],
  ['Clásico','estilo clásico elegante, molduras, tonos crema, madera oscura, lámpara de araña'],
];

let photoBlob=null,photoAspect=4/3,photoUrl=null,resultBlob=null,resultUrl=null,controller=null,timer=null;

function endpoint(){
  let override='';
  try{override=localStorage.getItem('homeai.renovationEndpoint')||''}catch{/* modo privado */}
  const meta=document.querySelector('meta[name="homeai-renovation-endpoint"]');
  return (override||(meta&&meta.content)||'').trim().replace(/\/+$/,'');
}

function injectUI(){
  const designView=$('#view-design');
  const anchor=$('#aiInteriorCard')||(designView&&designView.querySelector('.saved-finishes'));
  if(!designView||!anchor||$('#aiRenoCard'))return;
  const card=document.createElement('article');
  card.className='card ai-reno-card';
  card.id='aiRenoCard';
  const chips=STYLES.map(([label],i)=>`<button type="button" class="ai-reno-chip" data-reno-style="${i}" aria-pressed="false">${esc(label)}</button>`).join('');
  card.innerHTML=`<div class="card-heading"><div><h2>Visualiza tu reforma con IA</h2><p>Sube una foto de tu estancia, elige un estilo y mira cómo quedaría. La IA intenta mantener paredes, ventanas y distribución; es una orientación visual, no un proyecto técnico.</p></div></div>
<div class="ai-reno-body">
  <div class="ai-reno-off" id="aiRenoOff" hidden><b>Todavía no está activada.</b> Esta función necesita el servicio de IA de HomeAI, que aún no se ha configurado en esta instalación.</div>
  <div class="ai-reno-step"><span class="ai-reno-num">1</span><div class="ai-reno-step-body">
    <label class="btn btn-light ai-reno-upload" for="aiRenoFile">Elegir foto</label>
    <input type="file" id="aiRenoFile" accept="image/jpeg,image/png,image/webp" hidden>
    <span class="ai-reno-hint" id="aiRenoFileInfo">JPG, PNG o WebP. Mejor con buena luz y la estancia entera a la vista.</span>
    <img id="aiRenoThumb" class="ai-reno-thumb" alt="Foto elegida" hidden>
  </div></div>
  <div class="ai-reno-step"><span class="ai-reno-num">2</span><div class="ai-reno-step-body">
    <div class="ai-reno-chips" role="group" aria-label="Estilos rápidos">${chips}</div>
    <textarea id="aiRenoStyle" class="ai-orch-input" rows="2" maxlength="300" placeholder="O descríbelo tú: p. ej. salón nórdico, suelo de roble, sofá gris claro, mucha luz"></textarea>
    <label class="ai-reno-range">Cambio <span>Conservador</span><input type="range" id="aiRenoStrength" min="30" max="80" step="5" value="55" aria-label="Intensidad del cambio"><span>Creativo</span></label>
  </div></div>
  <label class="ai-reno-consent"><input type="checkbox" id="aiRenoConsent"> <span>Entiendo que, para generar la imagen, la foto (reducida y sin datos de ubicación) se envía al servicio de IA de HomeAI y a Hugging Face. No se guarda en ningún servidor.</span></label>
  <div class="ai-orch-actions"><button type="button" class="btn btn-dark" id="aiRenoRun">Generar visualización</button><button type="button" class="btn btn-light" id="aiRenoCancel" hidden>Cancelar</button><span id="aiRenoStatus" class="ai-orch-status" aria-live="polite"></span></div>
  <div class="ai-reno-wait" id="aiRenoWait" hidden><i></i><span>Transformando tu foto… suele tardar entre 10 y 60 segundos.</span></div>
  <div id="aiRenoResult" class="ai-reno-result" hidden>
    <div class="ai-reno-compare" id="aiRenoCompare" style="--pos:50%">
      <img id="aiRenoAfter" alt="Visualización generada por IA">
      <div class="ai-reno-before"><img id="aiRenoBefore" alt="Foto original"></div>
      <span class="ai-reno-tag ai-reno-tag-before">Antes</span><span class="ai-reno-tag ai-reno-tag-after">Después</span>
      <input type="range" id="aiRenoSlider" min="0" max="100" value="50" aria-label="Comparar antes y después">
    </div>
    <small>Imagen generada por IA a partir de tu foto. Puede cambiar detalles o inventar objetos: compruébala antes de tomar decisiones.</small>
    <div class="ai-orch-actions"><button type="button" class="btn btn-dark" id="aiRenoSave">Guardar en Archivos</button><button type="button" class="btn btn-light" id="aiRenoRetry">Probar otro estilo</button><button type="button" class="btn btn-light" id="aiRenoDiscard">Descartar</button></div>
  </div>
</div>`;
  anchor.after(card);
  $('#aiRenoFile').onchange=e=>pickPhoto(e.target.files&&e.target.files[0]);
  card.querySelectorAll('[data-reno-style]').forEach(b=>b.onclick=()=>pickStyle(b));
  $('#aiRenoStyle').oninput=()=>card.querySelectorAll('[data-reno-style]').forEach(b=>b.setAttribute('aria-pressed','false'));
  $('#aiRenoRun').onclick=run;
  $('#aiRenoCancel').onclick=()=>controller&&controller.abort('user');
  $('#aiRenoSlider').oninput=e=>$('#aiRenoCompare').style.setProperty('--pos',e.target.value+'%');
  $('#aiRenoSave').onclick=save;
  $('#aiRenoRetry').onclick=()=>{hideResult();$('#aiRenoStyle').focus()};
  $('#aiRenoDiscard').onclick=()=>{hideResult();status('Visualización descartada.')};
  if(!endpoint()){$('#aiRenoOff').hidden=false;$('#aiRenoRun').disabled=true}
}

function status(text){$('#aiRenoStatus').textContent=text}

function pickStyle(button){
  const [,prompt]=STYLES[Number(button.dataset.renoStyle)];
  $('#aiRenoStyle').value=prompt;
  $('#aiRenoCard').querySelectorAll('[data-reno-style]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
}

/* Reduce y re-codifica la foto en el navegador: aplica la orientación EXIF,
   limita el lado mayor a MAX_SIDE y exporta un JPEG nuevo (sin metadatos). */
async function preparePhoto(file){
  if(!ACCEPTED.includes(file.type)){
    const heic=/heic|heif/i.test(file.type)||/\.hei[cf]$/i.test(file.name);
    throw new Error(heic?'Las fotos HEIC del iPhone no se pueden leer aquí. Haz una captura de pantalla de la foto o cambia en Ajustes › Cámara › Formatos a «Más compatible».':'Formato no admitido. Usa una foto JPG, PNG o WebP.');
  }
  if(file.size>25*1024*1024)throw new Error('La foto pesa demasiado (máximo 25 MB).');
  let bitmap;
  try{bitmap=await createImageBitmap(file,{imageOrientation:'from-image'})}catch{throw new Error('No se pudo leer esa foto. Puede estar dañada; prueba con otra.')}
  const {width:w,height:h}=bitmap;
  if(Math.min(w,h)<256){bitmap.close();throw new Error('La foto es demasiado pequeña. Usa una de al menos 256 px por lado.')}
  if(Math.max(w,h)/Math.min(w,h)>3){bitmap.close();throw new Error('La foto es demasiado alargada (¿una panorámica?). Usa una foto normal de la estancia.')}
  const s=Math.min(1,MAX_SIDE/Math.max(w,h)),canvas=document.createElement('canvas');
  canvas.width=Math.round(w*s);canvas.height=Math.round(h*s);
  const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);
  ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();
  const blob=await new Promise(r=>canvas.toBlob(r,'image/jpeg',0.9));
  if(!blob)throw new Error('No se pudo preparar la foto. Prueba con otra.');
  return {blob,aspect:canvas.width/canvas.height};
}

async function pickPhoto(file){
  if(!file)return;
  hideResult();
  const info=$('#aiRenoFileInfo'),thumb=$('#aiRenoThumb');
  info.textContent='Preparando foto…';
  try{
    ({blob:photoBlob,aspect:photoAspect}=await preparePhoto(file));
    if(photoUrl)URL.revokeObjectURL(photoUrl);
    photoUrl=URL.createObjectURL(photoBlob);
    thumb.src=photoUrl;thumb.hidden=false;
    info.textContent=file.name;
  }catch(e){
    photoBlob=null;thumb.hidden=true;$('#aiRenoFile').value='';
    info.textContent=e.message;toast(e.message);
  }
}

const ERROR_TEXT={
  rate_limited:'Has hecho muchas visualizaciones seguidas. Espera un rato y vuelve a probar.',
  provider_rate_limited:'El servicio de IA está saturado ahora mismo. Espera un minuto y reinténtalo.',
  busy:'El servicio está ocupado con otras visualizaciones. Inténtalo en un minuto.',
  quota_exhausted:'La IA de HomeAI ha agotado su crédito por ahora. Vuelve a intentarlo más adelante.',
  model_loading:'El modelo de IA se está iniciando. Vuelve a intentarlo en unos segundos.',
  timeout:'La IA tardó demasiado en responder. Inténtalo de nuevo.',
  not_configured:'El servicio de IA no está disponible ahora mismo.',
  model_unsupported:'El servicio de IA no está disponible ahora mismo.',
};

async function errorMessage(res){
  let body={};
  try{body=await res.json()}catch{/* respuesta no JSON (p. ej. un proxy) */}
  const wait=Number(res.headers.get('Retry-After'));
  let text=ERROR_TEXT[body.error]||body.message||`El servicio de IA respondió con un error (${res.status}). Inténtalo de nuevo.`;
  if(wait>0&&wait<=3600&&/rate_limited|busy|model_loading|timeout/.test(body.error||''))text+=` (puedes reintentar en ~${wait<90?wait+' s':Math.ceil(wait/60)+' min'})`;
  return text;
}

async function run(){
  const url=endpoint();
  if(!url){toast('La visualización con IA aún no está activada.');return}
  if(!photoBlob){toast('Primero elige una foto de la estancia.');return}
  const style=$('#aiRenoStyle').value.trim();
  if(style.length<3){toast('Elige un estilo o descríbelo con tus palabras.');$('#aiRenoStyle').focus();return}
  if(!$('#aiRenoConsent').checked){toast('Marca la casilla de consentimiento para enviar la foto.');$('#aiRenoConsent').focus();return}
  const form=new FormData();
  form.append('image',photoBlob,'estancia.jpg');
  form.append('style',style);
  form.append('strength',String(Number($('#aiRenoStrength').value)/100));
  hideResult();busy(true);
  controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort('timeout'),CLIENT_TIMEOUT_MS);
  try{
    const res=await fetch(url+'/api/renovate',{method:'POST',body:form,signal:controller.signal});
    if(!res.ok)throw new Error(await errorMessage(res));
    const blob=await res.blob();
    if(!blob.type.startsWith('image/'))throw new Error('El servicio devolvió una respuesta inesperada. Inténtalo de nuevo.');
    showResult(blob);
    status('Listo. Desliza para comparar antes y después.');
  }catch(e){
    const reason=controller.signal.aborted?controller.signal.reason:null;
    const text=reason==='user'?'Generación cancelada.':reason==='timeout'?'La IA tardó demasiado en responder. Inténtalo de nuevo.':e instanceof TypeError?'No se pudo contactar con el servicio de IA. Revisa tu conexión e inténtalo de nuevo.':e.message;
    status(text);if(reason!=='user')toast(text);
  }finally{clearTimeout(timeout);controller=null;busy(false)}
}

function busy(on){
  $('#aiRenoRun').disabled=on;$('#aiRenoCancel').hidden=!on;$('#aiRenoWait').hidden=!on;
  $('#aiRenoFile').disabled=on;
  clearInterval(timer);
  if(on){const t0=Date.now();status('Enviando foto…');timer=setInterval(()=>status(`Generando… ${Math.round((Date.now()-t0)/1000)} s`),1000)}
}

function showResult(blob){
  resultBlob=blob;
  if(resultUrl)URL.revokeObjectURL(resultUrl);
  resultUrl=URL.createObjectURL(blob);
  $('#aiRenoAfter').src=resultUrl;$('#aiRenoBefore').src=photoUrl;
  const compare=$('#aiRenoCompare');
  // Ambas imágenes se muestran con la proporción de la foto original, aunque el
  // modelo devuelva otra: así el deslizador compara siempre la mismo encuadre.
  compare.style.aspectRatio=String(photoAspect);
  $('#aiRenoSlider').value=50;compare.style.setProperty('--pos','50%');
  $('#aiRenoResult').hidden=false;
}

function hideResult(){
  $('#aiRenoResult').hidden=true;
  if(resultUrl)URL.revokeObjectURL(resultUrl);
  resultUrl=null;resultBlob=null;$('#aiRenoAfter').removeAttribute('src');
}

async function save(){
  if(!resultBlob)return;
  const slug=$('#aiRenoStyle').value.trim().split(/[,.]/)[0].toLowerCase().replace(/[^a-z0-9áéíóúñü]+/gi,'-').replace(/^-|-$/g,'').slice(0,40)||'estilo';
  const file=new File([resultBlob],`reforma-ia-${slug}.jpg`,{type:'image/jpeg'});
  await handleDocument(file);
  status('Guardada en Archivos (solo en este dispositivo).');
}

injectUI();
})();
