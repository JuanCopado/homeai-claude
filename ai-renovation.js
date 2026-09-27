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

   Zonas: con "Solo algunas zonas", el servidor detecta pared/suelo/techo/
   mobiliario una vez por foto (/api/segment) y devuelve el mapa; el navegador
   lo guarda en memoria mientras el usuario toca zonas o ajusta con el pincel,
   y al generar envía la selección como máscara PNG. El servidor pega el
   resultado solo dentro de ella. Nada de esto se guarda en ningún servidor.

   Estilo: con la misma foto se pide /api/style (CLIP en el servidor). Si el
   modelo está seguro, se muestra "Parece: Rústico" sobre la foto (editable)
   y se marcan como sugeridos 2-3 estilos de destino coherentes; nunca se
   selecciona ninguno solo. Si duda, o la foto está vacía/es un exterior, no
   se afirma ningún estilo.

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
const ZONE_NAMES={pared:'Pared',suelo:'Suelo',techo:'Techo',mobiliario:'Mobiliario'};
// Estilo actual detectado -> nombre, adjetivo, y estilos de destino (etiquetas de STYLES) que suelen encajar.
const CURRENT_STYLES={
  moderno:['Moderno','moderna',['Nórdico','Japandi','Industrial']],
  rustico:['Rústico','rústica',['Nórdico','Japandi','Mediterráneo']],
  minimalista:['Minimalista','minimalista',['Japandi','Nórdico']],
  industrial:['Industrial','industrial',['Minimalista','Nórdico','Japandi']],
  escandinavo:['Escandinavo','escandinava',['Japandi','Minimalista','Mediterráneo']],
  clasico:['Clásico','clásica',['Minimalista','Japandi','Nórdico']],
  bohemio:['Bohemio','bohemia',['Nórdico','Mediterráneo','Japandi']],
  mediterraneo:['Mediterráneo','mediterránea',['Nórdico','Japandi','Minimalista']],
};
let current=null,stylePending=false,styleToken=0; // current = {style|null, source:'auto'|'user'|'none', reason}
// Estado de zonas de la foto actual: mapa del servidor + selección + ajustes a pincel.
let seg=null,segPending=false,segToken=0,mode='zones',tool='tap',brushSize=30,basePixels=null,drawQueued=false,painting=false,lastPoint=null;

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
    <div class="ai-reno-thumb-wrap"><img id="aiRenoThumb" class="ai-reno-thumb" alt="Foto elegida" hidden>
      <label class="ai-reno-style-tag" id="aiRenoStyleTag" hidden><span id="aiRenoStyleTagText">Detectando estilo…</span>
        <select id="aiRenoCurrent" aria-label="Estilo actual de la habitación (detectado automáticamente, puedes cambiarlo)"><option value="">—</option>${Object.entries(CURRENT_STYLES).map(([k,[n]])=>`<option value="${k}">${esc(n)}</option>`).join('')}<option value="none">Sin estilo claro</option></select></label></div>
    <small class="ai-reno-style-note" id="aiRenoStyleNote" hidden></small>
  </div></div>
  <label class="ai-reno-consent"><input type="checkbox" id="aiRenoConsent"> <span>Entiendo que, para detectar zonas y generar la imagen, la foto (reducida y sin datos de ubicación) se envía al servicio de IA de HomeAI y a Hugging Face. No se guarda en ningún servidor.</span></label>
  <div class="ai-reno-step"><span class="ai-reno-num">2</span><div class="ai-reno-step-body">
    <div class="ai-reno-mode" role="radiogroup" aria-label="Qué quieres cambiar">
      <label><input type="radio" name="aiRenoMode" value="zones" checked> Solo algunas zonas</label>
      <label><input type="radio" name="aiRenoMode" value="all"> Toda la foto</label>
    </div>
    <div class="ai-reno-zones" id="aiRenoZones" hidden>
      <div class="ai-reno-zone-chips" id="aiRenoZoneChips" role="group" aria-label="Zonas detectadas"></div>
      <div class="ai-reno-editor" id="aiRenoEditor"><canvas id="aiRenoCanvas" aria-label="Foto con las zonas seleccionadas resaltadas en verde. Toca una zona para seleccionarla o quitarla."></canvas><div class="ai-reno-seg-wait" id="aiRenoSegWait" hidden><i></i><span>Detectando pared, suelo, techo y muebles…</span></div></div>
      <div class="ai-reno-tools" role="group" aria-label="Herramienta">
        <button type="button" class="ai-reno-chip" data-reno-tool="tap" aria-pressed="true">Tocar zonas</button>
        <button type="button" class="ai-reno-chip" data-reno-tool="add" aria-pressed="false">＋ Pincel</button>
        <button type="button" class="ai-reno-chip" data-reno-tool="erase" aria-pressed="false">－ Borrar</button>
        <label class="ai-reno-brush" id="aiRenoBrushWrap" hidden>Tamaño <input type="range" id="aiRenoBrush" min="8" max="90" value="30" aria-label="Tamaño del pincel"></label>
        <button type="button" class="ai-reno-link" id="aiRenoResetEdits">Quitar ajustes</button>
      </div>
      <p class="ai-reno-summary" id="aiRenoSummary" aria-live="polite"></p>
    </div>
    <span class="ai-reno-hint" id="aiRenoModeHint">Elige una foto y marca la casilla de arriba para detectar las zonas.</span>
  </div></div>
  <div class="ai-reno-step"><span class="ai-reno-num">3</span><div class="ai-reno-step-body">
    <p class="ai-reno-suggest" id="aiRenoSuggest" hidden></p>
    <div class="ai-reno-chips" role="group" aria-label="Estilos rápidos">${chips}</div>
    <textarea id="aiRenoStyle" class="ai-orch-input" rows="2" maxlength="300" placeholder="O descríbelo tú: p. ej. salón nórdico, suelo de roble, sofá gris claro, mucha luz"></textarea>
    <label class="ai-reno-range">Cambio <span>Conservador</span><input type="range" id="aiRenoStrength" min="30" max="80" step="5" value="55" aria-label="Intensidad del cambio"><span>Creativo</span></label>
  </div></div>
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
  $('#aiRenoConsent').onchange=()=>{maybeSegment();maybeDetectStyle();updateZonesUI()};
  $('#aiRenoCurrent').onchange=e=>{const v=e.target.value;current={style:v&&v!=='none'?v:null,source:'user',reason:null};renderStyle()};
  card.querySelectorAll('input[name="aiRenoMode"]').forEach(r=>r.onchange=()=>{mode=r.value;maybeSegment();updateZonesUI()});
  card.querySelectorAll('[data-reno-tool]').forEach(b=>b.onclick=()=>setTool(b.dataset.renoTool));
  $('#aiRenoBrush').oninput=e=>{brushSize=Number(e.target.value)};
  $('#aiRenoResetEdits').onclick=()=>{if(seg){seg.edit.fill(0);drawSoon();updateSummary()}};
  const canvas=$('#aiRenoCanvas');
  canvas.addEventListener('pointerdown',pointerDown);
  canvas.addEventListener('pointermove',e=>{if(painting)paint(e)});
  ['pointerup','pointercancel','pointerleave'].forEach(t=>canvas.addEventListener(t,()=>{painting=false;lastPoint=null}));
  updateZonesUI();
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
  // Foto nueva: el mapa de zonas anterior deja de valer (y se descarta de memoria).
  seg=null;basePixels=null;segToken++;segPending=false;
  $('#aiRenoZoneChips').innerHTML='';delete $('#aiRenoModeHint').dataset.error;
  current=null;styleToken++;stylePending=false;
  maybeSegment();maybeDetectStyle();updateZonesUI();renderStyle();
}

/* ---------- Estilo actual ---------- */

async function maybeDetectStyle(){
  const url=endpoint();
  if(!url||!photoBlob||current||stylePending||!$('#aiRenoConsent').checked)return;
  const token=++styleToken;stylePending=true;renderStyle();
  const form=new FormData();form.append('image',photoBlob,'estancia.jpg');
  try{
    const res=await fetch(url+'/api/style',{method:'POST',body:form});
    if(!res.ok)throw new Error(String(res.status));
    const data=await res.json();
    if(token!==styleToken)return;
    current=data.suggest&&CURRENT_STYLES[data.style]?{style:data.style,source:'auto',reason:null}:{style:null,source:'none',reason:data.reason||null};
  }catch{
    // Sin detección (servicio antiguo, saturado…): no se afirma nada, pero el
    // usuario puede indicar el estilo a mano en el mismo selector.
    if(token!==styleToken)return;
    current={style:null,source:'none',reason:null};
  }finally{if(token===styleToken){stylePending=false;renderStyle()}}
}

function renderStyle(){
  const tag=$('#aiRenoStyleTag'),text=$('#aiRenoStyleTagText'),sel=$('#aiRenoCurrent'),note=$('#aiRenoStyleNote');
  tag.hidden=!photoBlob||(!current&&!stylePending);
  sel.hidden=stylePending;
  if(stylePending){text.textContent='Detectando estilo…';note.hidden=true}
  else if(current){
    sel.value=current.style||(current.source==='user'?'none':'');
    text.textContent=current.style?(current.source==='auto'?'Parece:':'Estilo actual:'):'Estilo actual:';
    note.hidden=!(current.source!=='user');
    note.textContent=current.source==='auto'?'Detectado automáticamente. Si no es así, cámbialo.':(current.reason?current.reason+' ':'')+'Puedes indicarlo tú si quieres sugerencias.';
  }
  renderSuggestions();
}

function renderSuggestions(){
  const box=$('#aiRenoSuggest'),info=current&&current.style&&CURRENT_STYLES[current.style];
  card().querySelectorAll('[data-reno-style]').forEach(b=>{
    const on=Boolean(info)&&info[2].includes(STYLES[Number(b.dataset.renoStyle)][0]);
    b.classList.toggle('is-suggested',on);
    b.title=on?'Sugerido para tu estancia':'';
  });
  box.hidden=!info;
  if(info)box.textContent=`Para una estancia ${info[1]} suelen encajar: ${info[2].join(', ')}. Son solo sugerencias; elige el que quieras.`;
}

/* ---------- Zonas ---------- */

function updateZonesUI(){
  const zonesMode=mode==='zones';
  const hint=$('#aiRenoModeHint');
  $('#aiRenoZones').hidden=!zonesMode||!(seg||segPending);
  $('#aiRenoSegWait').hidden=!segPending;
  const error=hint.dataset.error;
  // El motivo de un fallo de detección queda visible (no solo en un aviso
  // temporal), también en "Toda la foto", a la que se cambia automáticamente.
  hint.hidden=Boolean(seg||segPending)||(!zonesMode&&!error);
  if(!seg&&!segPending){
    hint.textContent=error||(!photoBlob?'Elige una foto para detectar sus zonas.':!$('#aiRenoConsent').checked?'Marca la casilla de consentimiento de arriba para detectar las zonas de la foto.':'Preparando…');
  }
  updateSummary();
}

async function maybeSegment(){
  const url=endpoint();
  if(mode!=='zones'||!url||!photoBlob||seg||segPending||!$('#aiRenoConsent').checked)return;
  const token=++segToken;segPending=true;delete $('#aiRenoModeHint').dataset.error;updateZonesUI();
  const form=new FormData();form.append('image',photoBlob,'estancia.jpg');
  try{
    const res=await fetch(url+'/api/segment',{method:'POST',body:form});
    if(!res.ok)throw new Error(res.status===404?'Este servicio de IA aún no detecta zonas.':await errorMessage(res));
    const data=await res.json();
    const zmap=await decodeMap(data.map,data.width,data.height,data.step||40);
    if(token!==segToken)return; // llegó tarde: el usuario ya cambió de foto
    seg={w:data.width,h:data.height,zmap,zones:data.zones,selected:new Set(),edit:new Uint8Array(data.width*data.height)};
    await loadBase();
    if(token!==segToken)return;
    renderZoneChips();drawSoon();
  }catch(e){
    if(token!==segToken)return;
    const text=(e instanceof TypeError?'No se pudo contactar con el servicio de IA.':e.message)+' Puedes transformar la foto entera.';
    $('#aiRenoModeHint').dataset.error=text;toast(text);
    card().querySelector('input[name="aiRenoMode"][value="all"]').checked=true;mode='all';
  }finally{if(token===segToken){segPending=false;updateZonesUI()}}
}

function card(){return $('#aiRenoCard')}

function decodeMap(dataUrl,w,h,step){
  return new Promise((resolve,reject)=>{
    const img=new Image();
    img.onload=()=>{
      const c=document.createElement('canvas');c.width=w;c.height=h;
      const ctx=c.getContext('2d');ctx.drawImage(img,0,0,w,h);
      const px=ctx.getImageData(0,0,w,h).data,out=new Uint8Array(w*h);
      for(let i=0;i<out.length;i++)out[i]=Math.round(px[i*4]/step);
      resolve(out);
    };
    img.onerror=()=>reject(new Error('No se pudo leer el mapa de zonas.'));
    img.src=dataUrl;
  });
}

function loadBase(){
  return new Promise((resolve,reject)=>{
    const img=new Image();
    img.onload=()=>{
      const c=$('#aiRenoCanvas');c.width=seg.w;c.height=seg.h;
      const ctx=c.getContext('2d');ctx.drawImage(img,0,0,seg.w,seg.h);
      basePixels=ctx.getImageData(0,0,seg.w,seg.h);resolve();
    };
    img.onerror=()=>reject(new Error('No se pudo mostrar la foto.'));
    img.src=photoUrl;
  });
}

function renderZoneChips(){
  $('#aiRenoZoneChips').innerHTML=seg.zones.filter(z=>z.selectable).map(z=>
    `<button type="button" class="ai-reno-chip ai-reno-zone-chip" data-reno-zone="${Number(z.id)}" aria-pressed="${seg.selected.has(z.id)}"${z.pct<0.5?' disabled title="No se ha detectado en esta foto"':''}>${esc(ZONE_NAMES[z.zone]||z.zone)} <small>${z.pct<0.5?'—':Math.round(Number(z.pct))+'%'}</small></button>`).join('');
  $('#aiRenoZoneChips').querySelectorAll('[data-reno-zone]').forEach(b=>b.onclick=()=>toggleZone(Number(b.dataset.renoZone)));
}

function toggleZone(id){
  if(!seg)return;
  const z=seg.zones[id];
  if(!z||!z.selectable)return;
  if(seg.selected.has(id))seg.selected.delete(id);else seg.selected.add(id);
  $('#aiRenoZoneChips').querySelectorAll('[data-reno-zone]').forEach(b=>b.setAttribute('aria-pressed',String(seg.selected.has(Number(b.dataset.renoZone)))));
  drawSoon();updateSummary();
}

function setTool(name){
  tool=name;
  card().querySelectorAll('[data-reno-tool]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.renoTool===name)));
  $('#aiRenoBrushWrap').hidden=name==='tap';
  $('#aiRenoCanvas').classList.toggle('is-painting',name!=='tap');
}

function canvasPoint(e){
  const c=$('#aiRenoCanvas'),r=c.getBoundingClientRect();
  return {x:Math.floor((e.clientX-r.left)/r.width*seg.w),y:Math.floor((e.clientY-r.top)/r.height*seg.h),scale:seg.w/r.width};
}

function pointerDown(e){
  if(!seg)return;
  const p=canvasPoint(e);
  if(p.x<0||p.y<0||p.x>=seg.w||p.y>=seg.h)return;
  if(tool==='tap'){
    const id=seg.zmap[p.y*seg.w+p.x],z=seg.zones[id];
    if(z&&z.selectable)toggleZone(id);
    else toast('Esa parte (ventana, puerta, espejo…) no es una zona seleccionable. Usa el pincel si quieres incluirla.');
    return;
  }
  painting=true;
  try{e.target.setPointerCapture(e.pointerId)}catch{/* navegadores antiguos */}
  paint(e);
}

function stamp(cx,cy,r,v){
  const x0=Math.max(0,cx-r),x1=Math.min(seg.w-1,cx+r),y0=Math.max(0,cy-r),y1=Math.min(seg.h-1,cy+r);
  for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++)if((x-cx)**2+(y-cy)**2<=r*r)seg.edit[y*seg.w+x]=v;
}

function paint(e){
  const p=canvasPoint(e),r=Math.max(2,Math.round(brushSize*p.scale/2)),v=tool==='add'?1:2;
  // Rellena el hueco desde el punto anterior: los eventos del puntero llegan
  // espaciados y, sin esto, un trazo rápido sale como una cadena de círculos.
  const from=lastPoint||p,steps=Math.max(1,Math.ceil(Math.hypot(p.x-from.x,p.y-from.y)/(r/2)));
  for(let i=1;i<=steps;i++)stamp(Math.round(from.x+(p.x-from.x)*i/steps),Math.round(from.y+(p.y-from.y)*i/steps),r,v);
  lastPoint=p;
  drawSoon();updateSummary();
}

function selectionMask(){
  const n=seg.w*seg.h,m=new Uint8Array(n);
  for(let i=0;i<n;i++){const ed=seg.edit[i];m[i]=ed===1||(ed!==2&&seg.selected.has(seg.zmap[i]))?1:0}
  return m;
}

function drawSoon(){
  if(drawQueued)return;drawQueued=true;
  requestAnimationFrame(()=>{drawQueued=false;draw()});
}

/* Foto con la selección en verde y el resto ligeramente atenuado: así queda
   claro qué se va a modificar antes de confirmar. */
function draw(){
  if(!seg||!basePixels)return;
  const c=$('#aiRenoCanvas'),ctx=c.getContext('2d'),m=selectionMask();
  const out=ctx.createImageData(seg.w,seg.h),src=basePixels.data,dst=out.data;
  for(let i=0,j=0;i<m.length;i++,j+=4){
    if(m[i]){dst[j]=src[j]*0.5+40*0.5;dst[j+1]=src[j+1]*0.5+190*0.5;dst[j+2]=src[j+2]*0.5+110*0.5}
    else{dst[j]=src[j]*0.8;dst[j+1]=src[j+1]*0.8;dst[j+2]=src[j+2]*0.8}
    dst[j+3]=255;
  }
  ctx.putImageData(out,0,0);
}

function selectedZoneNames(m){
  // Zonas que forman al menos el 3% de lo seleccionado (incluidos los ajustes a
  // pincel): así el resumen nombra todo lo que se verá en verde, no solo lo mayor.
  const counts=new Map();let total=0;
  for(let i=0;i<m.length;i++)if(m[i]){total++;const z=seg.zones[seg.zmap[i]];counts.set(z.zone,(counts.get(z.zone)||0)+1)}
  return {total,names:[...counts].filter(([,c])=>c>=0.03*total).sort((a,b)=>b[1]-a[1]).map(([z])=>z)};
}

function updateSummary(){
  const out=$('#aiRenoSummary'),run=$('#aiRenoRun');
  if(mode!=='zones'||!seg){run.textContent=mode==='zones'?'Generar visualización':'Generar visualización de toda la foto';out.textContent='';return}
  const {total,names}=selectedZoneNames(selectionMask());
  if(!total){out.textContent='Toca en la foto (o en los botones) la zona que quieres cambiar: pared, suelo, techo o mobiliario.';run.textContent='Generar visualización';return}
  const label=names.map(z=>(ZONE_NAMES[z]||(z==='ventana/puerta'?'ventanas/puertas':'otras partes')).toLowerCase()).join(', ')||'zona marcada';
  out.textContent=`Se modificará lo marcado en verde: ${label} (${Math.round(100*total/(seg.w*seg.h))}% de la foto). El resto se queda como está.`;
  run.textContent=`Generar solo en: ${label}`;
}

function maskBlob(){
  const m=selectionMask(),c=document.createElement('canvas');c.width=seg.w;c.height=seg.h;
  const ctx=c.getContext('2d'),img=ctx.createImageData(seg.w,seg.h);
  for(let i=0,j=0;i<m.length;i++,j+=4){const v=m[i]?255:0;img.data[j]=img.data[j+1]=img.data[j+2]=v;img.data[j+3]=255}
  ctx.putImageData(img,0,0);
  return new Promise(r=>c.toBlob(r,'image/png'));
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
  if(mode==='zones'){
    if(segPending){toast('Espera un momento: se están detectando las zonas.');return}
    if(!seg){toast('Todavía no hay zonas detectadas. Elige «Toda la foto» o vuelve a intentarlo.');return}
    const {total,names}=selectedZoneNames(selectionMask());
    if(!total){toast('Selecciona al menos una zona tocándola en la foto.');return}
    form.append('mask',await maskBlob(),'zonas.png');
    form.append('zones',names.join(','));
  }
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
  card().querySelectorAll('input[name="aiRenoMode"],[data-reno-zone],[data-reno-tool]').forEach(el=>{el.disabled=on});
  if(!on&&seg)renderZoneChips(); // restaura el estado propio de cada zona (p. ej. las no detectadas)
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
  // modelo devuelva otra: así el deslizador compara siempre el mismo encuadre.
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
