/* Asistente IA local para el orquestador de lenguaje natural (punto 7/8 del
   encargo de Juan: "tengo 25.000€ para reformar, dame la mejor propuesta").
   Usa WebLLM (@mlc-ai/web-llm) cargado bajo demanda desde CDN, exactamente
   igual que loadTesseract() en app.js: nada se descarga hasta que el usuario
   pulsa el botón, y si falla o el navegador no soporta WebGPU, la app sigue
   funcionando igual que antes (degradación con gracia).
   CAPA GENERATIVA ESTRICTA: esta función SOLO lee project (rooms, costs,
   style) para dar contexto al modelo. Nunca escribe project.rooms,
   project.costs ni ninguna geometría — su salida es texto de solo lectura
   que el usuario decide si aplicar a mano. Ver DIGITAL_TWIN_ARCHITECTURE.md
   sección 2 y PROVEEDORES_IA.md. */
(()=>{'use strict';
const MODEL_ID='Llama-3.2-3B-Instruct-q4f16_1-MLC';
const CDN_URL='https://cdn.jsdelivr.net/npm/@mlc-ai/web-llm@0.2.85/+esm';
let engine=null;

function injectUI(){
  const budgetView=$('#view-budget');
  if(!budgetView||$('#aiOrchestratorCard'))return;
  const card=document.createElement('article');
  card.className='card ai-orch-card';
  card.id='aiOrchestratorCard';
  card.innerHTML=`<div class="card-heading"><div><h2>Asistente IA (experimental, local)</h2><p>Describe tu presupuesto y tus necesidades; recibe una orientación con alternativas. No modifica tu presupuesto ni tus estancias — decides tú qué aplicar.</p></div></div><div class="ai-orch-body"><textarea id="aiOrchInput" class="ai-orch-input" rows="3" placeholder="Ej.: Tengo 25.000€ para reformar, somos 4 personas, quiero priorizar la cocina..."></textarea><div class="ai-orch-actions"><button type="button" class="btn btn-dark" id="aiOrchRun">Pedir recomendación</button><span id="aiOrchStatus" class="ai-orch-status" aria-live="polite"></span></div><div id="aiOrchOutput" class="ai-orch-output" aria-live="polite" hidden></div></div><div class="info-strip"><span>ⓘ</span><p>La primera vez, este asistente descarga un modelo de IA (más de 1&nbsp;GB) y lo ejecuta enteramente en tu navegador — tu proyecto no se envía a ningún servidor. Necesita un navegador con soporte WebGPU (Chrome o Edge recientes). Sus respuestas son orientativas: revísalas antes de aplicarlas a tu presupuesto real.</p></div>`;
  const lastInfoStrip=budgetView.querySelector('.info-strip');
  if(lastInfoStrip)lastInfoStrip.after(card);else budgetView.appendChild(card);
  $('#aiOrchRun').onclick=runOrchestrator;
}

function projectContext(){
  const rooms=project.rooms.length?project.rooms.map(r=>`${r.name} (${fmt(r.w)}×${fmt(r.d)} m${r.verified?'':', medida sin confirmar'})`).join('; '):'ninguna estancia medida todavía';
  const total=budgetTotal();
  return `Estancias del proyecto: ${rooms}.\nTotal de partidas ya introducidas en el presupuesto: ${total?money(total):'sin precios todavía'} (puede estar incompleto).\nEstilo guardado: ${project.style||'sin definir'}.`;
}

async function loadEngine(onProgress){
  if(engine)return engine;
  if(!('gpu' in navigator))throw new Error('no-webgpu');
  const webllm=await import(/* webpackIgnore: true */ CDN_URL);
  engine=await webllm.CreateMLCEngine(MODEL_ID,{initProgressCallback:onProgress});
  return engine;
}

async function runOrchestrator(){
  const input=$('#aiOrchInput').value.trim();
  if(!input){toast('Escribe tu presupuesto y necesidades primero.');return}
  const status=$('#aiOrchStatus'),output=$('#aiOrchOutput'),btn=$('#aiOrchRun');
  btn.disabled=true;output.hidden=true;status.textContent='Comprobando compatibilidad…';
  try{
    const eng=await loadEngine(p=>{status.textContent=p&&p.text?p.text:'Cargando modelo de IA…'});
    status.textContent='Pensando…';
    const messages=[
      {role:'system',content:'Eres un asesor de reformas de vivienda para la app HomeAI. Responde siempre en español, de forma breve y práctica. Propón hasta 3 alternativas (económica, equilibrada, premium) con una frase de justificación cada una, usando SOLO los datos del proyecto que se te dan y lo que pide el usuario. No inventes medidas ni precios exactos que no se te han dado. Deja claro que son orientativas, no un presupuesto cerrado, y que el usuario debe confirmarlas.'},
      {role:'user',content:`${projectContext()}\n\nPetición del usuario: ${input}`}
    ];
    const reply=await eng.chat.completions.create({messages});
    output.textContent=reply.choices?.[0]?.message?.content||'No se obtuvo respuesta del asistente.';
    output.hidden=false;status.textContent='Listo. Recuerda: es una orientación, no un presupuesto cerrado.';
  }catch(e){
    output.hidden=false;
    output.textContent=e&&e.message==='no-webgpu'
      ?'Tu navegador no soporta WebGPU, así que este asistente local no puede ejecutarse aquí. Prueba con una versión reciente de Chrome o Edge en un ordenador, o completa el presupuesto manualmente.'
      :'No se pudo cargar el asistente de IA ahora (puede ser tu conexión o que el navegador se quedó sin memoria para el modelo). Puedes seguir usando la guía de estilo o completar el presupuesto manualmente.';
    status.textContent='';
  }finally{btn.disabled=false}
}

injectUI();
})();
