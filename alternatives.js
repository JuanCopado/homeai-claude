/* HomeAI: named design alternatives and explicit purchasing handoff. */
(() => {
  'use strict';
  const clone = value => structuredClone(value);
  const alternativesFor = room => project.designAlternatives?.[roomKey(room)] || [];
  const styleLabel = d => styleOptions.find(s => s.id === d.style)?.name || d.style || 'Personalizado';
  const css = document.createElement('style');
  css.textContent = `.alternatives-panel{margin-top:24px;padding:26px}.alternatives-heading{display:flex;justify-content:space-between;align-items:start;gap:16px;flex-wrap:wrap}.alternatives-heading h2{margin:7px 0}.alternatives-heading p,.alternative-card small,.alternatives-note{color:var(--muted,#647067);font-size:13px;line-height:1.6}.alternatives-actions{display:flex;gap:8px;flex-wrap:wrap}.alternatives-panel button,.alternatives-dialog button{min-height:42px;border:1px solid #cbd6cc;border-radius:9px;background:#fff;padding:10px 14px;cursor:pointer;color:#263c2d}.alternatives-panel button.primary,.alternatives-dialog button.primary{background:#264c39;color:white;border-color:#264c39}.alternatives-panel button:disabled{opacity:.5;cursor:default}.alternatives-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(225px,1fr));gap:14px;margin-top:18px}.alternative-card{border:1px solid #dce3db;border-radius:14px;padding:18px;background:#fff}.alternative-card h3{margin:0 0 5px}.alternative-card p{font-size:13px;line-height:1.7;margin:12px 0}.alternative-swatches{display:flex;gap:5px;margin:12px 0}.alternative-swatches i{height:27px;width:48px;border:1px solid #0001;border-radius:6px}.alternative-card .alternatives-actions button{font-size:12px;padding:8px 11px}.alternatives-table-wrap{overflow:auto;margin-top:18px}.alternatives-table{border-collapse:collapse;width:100%;font-size:13px}.alternatives-table td,.alternatives-table th{padding:12px;text-align:left;border-bottom:1px solid #e0e5df;min-width:145px;vertical-align:top}.alternatives-dialog label{display:block;margin:18px 0}.alternatives-dialog input{width:100%;padding:12px;border:1px solid #cbd6cc;border-radius:8px;margin-top:8px}.alternatives-dialog ul{padding-left:20px;max-height:300px;overflow:auto;font-size:14px;line-height:1.8}.alternatives-empty{padding:22px 0;color:#647067;font-size:14px}@media(max-width:600px){.alternatives-panel{padding:18px}.alternatives-grid{grid-template-columns:1fr}.alternatives-heading>.alternatives-actions{width:100%}.alternatives-heading>.alternatives-actions button{flex:1}}`;
  document.head.append(css);
  function modal(content) {
    $('#modalContent').innerHTML = `<div class="alternatives-dialog">${content}</div>`;
    $('#modal').classList.add('open');
  }
  function saveAlternative() {
    const room = selectedRoom();
    if (!room) return toast('Añade una estancia para guardar alternativas.');
    const snapshot = clone(designDraft), key = roomKey(room);
    modal(`<span class="eyebrow">EXPLORA SIN PERDER TUS IDEAS</span><h2>Guardar una alternativa</h2><p>Conserva esta combinación de ${esc(room.name)} para recuperarla y compararla después.</p><form id="alternativeForm"><label>Nombre de la propuesta<input id="alternativeName" maxlength="70" required value="${esc('Propuesta '+(alternativesFor(room).length+1))}" placeholder="Ej. Mediterráneo luminoso"></label><button class="primary" type="submit">Guardar alternativa</button></form>`);
    $('#alternativeForm').onsubmit = e => {
      e.preventDefault();
      const name = $('#alternativeName').value.trim();
      if (!name) return $('#alternativeName').focus();
      checkpoint();
      project.designAlternatives ||= {};
      project.designAlternatives[key] ||= [];
      project.designAlternatives[key].push({id:stableRoomId(),name,createdAt:new Date().toISOString(),design:snapshot});
      saveSoon(); $('#modal').classList.remove('open'); renderAlternatives(); toast('Alternativa guardada: '+name);
    };
    $('#alternativeName').focus(); $('#alternativeName').select();
  }
  function restoreAlternative(id) {
    const room = selectedRoom(), version = alternativesFor(room).find(v => v.id === id);
    if (!version) return;
    checkpoint(); designDraft = clone(version.design); storeDesignDraft(); renderDesign(true);
    toast('Alternativa recuperada. Guarda el diseño si quieres aprobarla.');
  }
  function removeAlternative(id) {
    const room = selectedRoom(), key = roomKey(room), version = alternativesFor(room).find(v => v.id === id);
    if (!version) return;
    modal(`<h2>Eliminar alternativa</h2><p>Se eliminará «${esc(version.name)}» de ${esc(room.name)}. El diseño actual se conserva.</p><div class="alternatives-actions"><button id="keepAlternative">Conservar</button><button id="confirmRemoveAlternative">Eliminar alternativa</button></div>`);
    $('#keepAlternative').onclick = () => $('#modal').classList.remove('open');
    $('#confirmRemoveAlternative').onclick = () => { checkpoint(); project.designAlternatives[key] = project.designAlternatives[key].filter(v => v.id !== id); saveSoon(); $('#modal').classList.remove('open'); renderAlternatives(); toast('Alternativa eliminada.'); };
  }
  function purchaseItems() {
    const out = [];
    for (const room of project.rooms) {
      const key = roomKey(room), d = project.finishes?.[key];
      if (!d) continue;
      const add = (slot, label, value, unit = 'ud', qty = '') => {
        if (!value || /^sin\b/i.test(value)) return;
        out.push({sourceDesignKey:key+':'+slot,name:`${room.name} · ${label}: ${value}`,unit,qtyType:'manual',qty,price:''});
      };
      add('floor','Suelo',d.material,'m²',room.verified !== false && area(room)>0 ? Number(area(room).toFixed(2)) : '');
      for (const [detail,value] of Object.entries(d.roomDetails||{})) if(!['Distribución','Tipo de reforma','Uso principal','Plazas previstas','Ventilación'].includes(detail)) add('detail-'+detail,detail,value);
      add('wall','Pared', [d.wallFinish,d.wallName].filter(Boolean).join(' · '),'m²');
      if (roomType(room)==='bath') {
        add('faucet','Grifería',d.faucet);
        for (const field of bathDetailOptions) add('bath-'+field.key,field.label,d.bathDetails?.[field.key]);
      } else {
        for (const field of decorOptions) {const kind=roomType(room),skip=kind==='kitchen'?['furniture','diningTable','rugs','textiles','storage']:kind==='bedroom'?['furniture','diningTable']:[];if(!skip.includes(field.key))add('decor-'+field.key,field.label,d.decor?.[field.key]);}
      }
    }
    return out;
  }
  function preparePurchases() {
    const all = purchaseItems(), pending = all.filter(x => !project.costs.some(c => c.sourceDesignKey === x.sourceDesignKey));
    if (!all.length) return toast('Guarda primero el diseño de una estancia.');
    modal(`<span class="eyebrow">DEL DISEÑO A LAS COMPRAS</span><h2>Preparar partidas para cotizar</h2><p>${pending.length ? `${pending.length} partidas nuevas a partir de tus diseños guardados.` : 'Estas partidas ya están en tu presupuesto.'} Los precios quedan vacíos para introducir cotizaciones reales.</p><p class="alternatives-note">El suelo utiliza solo la superficie confirmada, sin merma. Mide paredes, cuenta unidades y confirma cantidades antes de comprar. Las partidas existentes se conservan; si cambias de material, edítalas en Presupuesto.</p>${pending.length ? `<ul>${pending.map(x=>`<li>${esc(x.name)}${x.qty ? ` · ${fmt(x.qty)} ${esc(x.unit)}` : ' · cantidad pendiente'}</li>`).join('')}</ul>` : ''}<div class="alternatives-actions">${pending.length?'<button class="primary" id="confirmPurchases">Añadir al presupuesto</button>':''}<button id="openPurchaseBudget">Ver presupuesto</button></div>`);
    $('#openPurchaseBudget').onclick=()=>{$('#modal').classList.remove('open');goView('budget')};
    if (pending.length) $('#confirmPurchases').onclick=()=>{
      checkpoint();
      const additions = pending.filter(x => !project.costs.some(c => c.sourceDesignKey===x.sourceDesignKey));
      project.costs.push(...additions); saveSoon(); renderBudget(); renderOverview(); $('#modal').classList.remove('open'); goView('budget'); toast(`${additions.length} partidas añadidas. Completa cantidades y precios.`);
    };
  }
  function renderAlternatives() {
    const view = $('#view-design'); if (!view) return;
    let host = $('#designAlternativesPanel');
    if (!host) { host=document.createElement('article'); host.id='designAlternativesPanel'; host.className='card alternatives-panel'; view.append(host); }
    const room=selectedRoom(), versions=alternativesFor(room), approved=room&&project.finishes?.[roomKey(room)];
    const roomDetailKeys=[...new Set(versions.flatMap(version=>Object.keys(version.design.roomDetails||{})))];
    host.innerHTML=`<div class="alternatives-heading"><div><span class="eyebrow">GUARDA · COMPARA · DECIDE</span><h2>Alternativas${room?' de '+esc(room.name):' de diseño'}</h2><p>Prueba nuevas combinaciones y conserva tus favoritas antes de decidir.</p></div><div class="alternatives-actions"><button class="primary" id="saveDesignAlternative" ${room?'':'disabled'}>＋ Guardar alternativa</button><button id="prepareDesignPurchases">Preparar compras →</button></div></div>${versions.length?`<div class="alternatives-grid">${versions.map(v=>`<article class="alternative-card"><h3>${esc(v.name)}</h3><small>${esc(styleLabel(v.design))}${approved&&designSignature(approved)===designSignature(v.design)?' · Diseño guardado':''}</small><div class="alternative-swatches"><i style="background:${/^#[\da-f]{3,8}$/i.test(v.design.wallColor||'')?v.design.wallColor:'#eee'}" title="Pared"></i><i style="background:${/^#[\da-f]{3,8}$/i.test(v.design.floorColor||'')?v.design.floorColor:'#ccc'}" title="Suelo"></i></div><p><b>Pared</b> · ${esc(v.design.wallName||'Personalizada')}<br><b>Suelo</b> · ${esc(v.design.material||'Pendiente')}</p><div class="alternatives-actions"><button data-restore-alternative="${esc(v.id)}">Recuperar</button><button data-delete-alternative="${esc(v.id)}" aria-label="Eliminar ${esc(v.name)}">Eliminar</button></div></article>`).join('')}</div>${versions.length>1?`<details class="alternatives-table-wrap"><summary>Comparar ${versions.length} alternativas en detalle</summary><table class="alternatives-table"><thead><tr><th>Selección</th>${versions.map(v=>`<th>${esc(v.name)}</th>`).join('')}</tr></thead><tbody>${[['Estilo',d=>styleLabel(d)],['Color',d=>d.wallName],['Pared',d=>d.wallFinish],['Suelo',d=>d.material],...(roomType(room)==='bath'?[['Baño',d=>d.bath],['Ducha',d=>d.bathDetails?.shower],['Lavabo',d=>d.bathDetails?.vanity],['Grifería',d=>d.faucet]]:[['Mobiliario',d=>d.decor?.furniture],['Textiles',d=>d.decor?.textiles]]),['Iluminación',d=>d.decor?.lighting],...roomDetailKeys.map(key=>[key,d=>d.roomDetails?.[key]])].map(([label,get])=>`<tr><th>${esc(label)}</th>${versions.map(v=>`<td>${esc(get(v.design)||'Por decidir')}</td>`).join('')}</tr>`).join('')}</tbody></table></details>`:''}`:'<div class="alternatives-empty">Guarda la primera propuesta; después cambia el estilo o los materiales y guarda otra para compararlas aquí.</div>'}`;
    $('#saveDesignAlternative').onclick=saveAlternative;
    $('#prepareDesignPurchases').onclick=preparePurchases;
    host.querySelectorAll('[data-restore-alternative]').forEach(b=>b.onclick=()=>restoreAlternative(b.dataset.restoreAlternative));
    host.querySelectorAll('[data-delete-alternative]').forEach(b=>b.onclick=()=>removeAlternative(b.dataset.deleteAlternative));
  }
  const originalRenderDesign=renderDesign;
  renderDesign=function(...args){const result=originalRenderDesign.apply(this,args);renderAlternatives();return result};
  const originalRenderFinishList=renderFinishList;
  renderFinishList=function(...args){const result=originalRenderFinishList.apply(this,args);renderAlternatives();return result};
  renderAlternatives();
})();
