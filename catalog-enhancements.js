/* HomeAI catalog discovery. Load as a classic deferred script after app.js. */
(() => {
  'use strict';
  const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es');
  const families = {
    estilo: [
      ['Naturales y serenos', ['calido','japandi','nordico','wabisabi','organicmodern','minimalista']],
      ['Mediterráneos y costeros', ['mediterraneo','tropical','costero','coastalmodern']],
      ['Urbanos y actuales', ['contemporaneo','industrial','softindustrial','monochrome']],
      ['Clásicos y elegantes', ['clasico','artdeco','quietluxury','parisian','colonial']],
      ['Rústicos y personales', ['rustico','boho','midcentury','maximalista','farmhouse','retro70','eclectic']]
    ],
    suelo: [
      ['Madera y parqué', ['Roble natural','Roble blanqueado','Roble ahumado','Nogal natural','Haya clara','Pino nórdico','Espiga roble','Punta Hungría','Parquet mosaico','Bambú natural']],
      ['Laminado y vinilo', ['Laminado AC4','Laminado AC5','SPC roble claro','Vinilo efecto madera']],
      ['Porcelánico y cerámica', ['Porcelánico marfil','Porcelánico cemento','Porcelánico gran formato','Porcelánico antideslizante','Ladrillo artesanal','Azulejo tipo zellige','Baldosa hexagonal']],
      ['Piedra natural', ['Mármol crema','Mármol oscuro','Piedra caliza','Travertino','Pizarra oscura','Mosaico de piedra']],
      ['Continuos y decorativos', ['Terrazo cálido','Terrazo de color','Baldosa hidráulica','Microcemento arena','Microcemento gris','Cemento pulido']],
      ['Corcho, textil y linóleo', ['Corcho natural','Moqueta de lana','Linóleo natural']]
    ]
  };
  const filters = {estilo: '', suelo: ''};
  const palettes = [
    ['Luz de arena','Arena','Roble natural','Lino natural','Latón satinado','#b7956f'],
    ['Calma salvia','Salvia','Roble blanqueado','Algodón crudo','Acero cepillado','#879582'],
    ['Azul de costa','Azul niebla','Roble blanqueado','Rayas costeras','Níquel satinado','#7e9da4'],
    ['Tierra y cal','Blanco cal','Ladrillo artesanal','Lino lavado','Bronce envejecido','#bf775f'],
    ['Oliva y nogal','Oliva suave','Nogal natural','Bouclé marfil','Latón satinado','#78553e'],
    ['Piedra serena','Piedra','Piedra caliza','Lino natural','Acero cepillado','#c8c5b8'],
    ['Contraste suave','Gris niebla','Roble ahumado','Lana jaspeada','Negro mate','#383b38'],
    ['Rosa mineral','Rosa empolvado','Terrazo cálido','Algodón crudo','Latón satinado','#d7b6a3'],
    ['Noche elegante','Azul profundo','Espiga roble','Terciopelo oliva','Latón satinado','#dacba7'],
    ['Marfil clásico','Marfil','Mármol crema','Bouclé marfil','Bronce envejecido','#a3917c'],
    ['Arcilla contemporánea','Arcilla','Microcemento arena','Lino lavado','Negro mate','#bf775f'],
    ['Lavanda y roble','Lavanda gris','Roble natural','Lana jaspeada','Níquel satinado','#aa91a7']
  ].map(([name, wall, floor, textile, hardware, accent], id) => ({id,name,wall,floor,textile,hardware,accent}));
  const style = document.createElement('style');
  style.textContent = `
    .catalog-family-filters{display:flex;flex-wrap:wrap;gap:7px;margin:14px 0 18px}
    .catalog-family-filters button{border:1px solid #d9ded5;border-radius:99px;background:#fff;color:#4b5b4d;font:inherit;font-size:12px;padding:9px 12px;cursor:pointer;min-height:36px}
    .catalog-family-filters button[aria-pressed="true"]{background:#294c38;color:#fff;border-color:#294c38}
    .homeai-palettes{margin:0 0 24px;border-bottom:1px solid #e2e5dc;padding-bottom:22px}
    .homeai-palettes h4{margin:0 0 6px;font-size:16px}.homeai-palettes p{font-size:12px;line-height:1.6;color:#667365;margin:0 0 12px}
    .homeai-palette-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
    .homeai-palette{display:flex;flex-direction:column;text-align:left;gap:6px;border:1px solid #dde1d8;border-radius:12px;background:#fff;padding:12px;cursor:pointer;color:#26372b;font:inherit;min-width:0}
    .homeai-palette[aria-pressed="true"]{outline:2px solid #587b60;outline-offset:-2px;background:#f0f5ed}
    .homeai-palette b{font-size:12px}.homeai-palette small{font-size:10px;line-height:1.55;color:#687165}.homeai-palette-swatches{display:flex;width:100%;height:29px;border-radius:5px;overflow:hidden}.homeai-palette-swatches i{flex:1}.homeai-palette-swatches i:first-child{flex:2}
    .homeai-palette [data-palette-action]{font-size:10px;color:#366546;font-weight:700}
    .catalog-family-filters button:focus-visible,.homeai-palette:focus-visible{outline:3px solid #70947a;outline-offset:3px}
    .homeai-filter-empty{padding:18px;background:#f3f4ef;border-radius:12px;font-size:13px;color:#53614f;margin:12px 0}
    .homeai-filter-empty button{display:block;margin-top:9px;background:none;border:0;color:#2b6140;font:inherit;text-decoration:underline;cursor:pointer}
    .homeai-custom-color{border:1px solid #dde1d8;border-radius:12px;padding:14px;margin:0 0 18px;background:#fafbf7}.homeai-custom-color h4{font-size:14px;margin:0 0 5px}.homeai-custom-color p{font-size:11px;line-height:1.6;margin:0 0 12px;color:#677062}.homeai-color-fields{display:grid;grid-template-columns:46px 95px minmax(0,1fr);gap:8px;align-items:end}.homeai-color-fields label{display:flex;flex-direction:column;gap:5px;font-size:10px;color:#53614f}.homeai-color-fields input{box-sizing:border-box;width:100%;min-width:0;height:38px;border:1px solid #cdd6c9;border-radius:7px;background:#fff;padding:7px;font:inherit;font-size:12px;color:#243b2a}.homeai-color-fields input[type=color]{padding:3px;cursor:pointer}.homeai-custom-color button{margin-top:10px;border:0;border-radius:7px;padding:10px 15px;background:#294c38;color:white;font:inherit;font-size:12px;cursor:pointer}.homeai-custom-color input:focus-visible,.homeai-custom-color button:focus-visible{outline:3px solid #70947a;outline-offset:2px}
    .homeai-palette[hidden],.homeai-filter-empty[hidden]{display:none!important}
    @media(max-width:420px){.homeai-palette-grid{grid-template-columns:1fr 1fr}.homeai-palette{padding:9px}.catalog-family-filters{gap:5px}.catalog-family-filters button{font-size:11px;padding:8px 10px}}
  `;
  document.head.append(style);
  for (const [category, groups] of Object.entries(families)) {
    const host = document.createElement('div');
    host.className = 'catalog-family-filters';
    host.setAttribute('role', 'group');
    host.setAttribute('aria-label', category === 'suelo' ? 'Filtrar por familia de suelo' : 'Filtrar por familia de estilo');
    ['', ...groups.map(group => group[0])].forEach(name => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = name || 'Todos';
      button.setAttribute('aria-pressed', String(!name));
      button.addEventListener('click', () => {
        filters[category] = name;
        for (const sibling of host.children) sibling.setAttribute('aria-pressed', String(sibling === button));
        filterCatalog();
      });
      host.append(button);
    });
    document.getElementById(category === 'suelo' ? 'floorCatalog' : 'styleCatalog').before(host);
  }
  const section = document.createElement('section');
  section.className = 'homeai-palettes';
  section.setAttribute('aria-label', 'Paletas coordinadas');
  section.innerHTML = '<h4>Combina con confianza</h4><p>12 paletas coordinadas. Cada una aplica pared, suelo, textil y herrajes a tu borrador; después puedes ajustar cada detalle.</p><div class="homeai-palette-grid"></div>';
  for (const palette of palettes) {
    const color = colorOptions.find(item => item[1] === palette.wall);
    const floor = floorOptions.find(item => item.name === palette.floor);
    if (!color || !floor) continue;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'homeai-palette';
    button.dataset.homeaiPalette = palette.id;
    button.setAttribute('aria-pressed', 'false');
    button.innerHTML = `<span class="homeai-palette-swatches" aria-hidden="true"><i style="background:${color[0]}"></i><i style="background:${floor.color}"></i><i style="background:${palette.accent}"></i></span><b>${palette.name}</b><small>${palette.wall} · ${palette.floor}<br>${palette.textile} · ${palette.hardware}</small><span data-palette-action>Aplicar combinación →</span>`;
    button.addEventListener('click', () => {
      checkpoint();
      Object.assign(designDraft, {wallColor:color[0],wallName:palette.wall,material:floor.name,floorKind:floor.kind,floorColor:floor.color});
      designDraft.decor = {...designDraft.decor,textiles:palette.textile,hardware:palette.hardware};
      storeDesignDraft();
      renderDesign(true);
      toast('Paleta '+palette.name+' aplicada al borrador. Puedes personalizarla o deshacer.');
    });
    section.querySelector('.homeai-palette-grid').append(button);
  }
  document.getElementById('designColors').before(section);
  const customColor = document.createElement('form');
  customColor.className = 'homeai-custom-color';
  customColor.innerHTML = '<h4>Tu propio color</h4><p>Elige cualquier tono o introduce su código HEX. La muestra en pantalla es orientativa; comprueba una muestra física antes de pintar.</p><div class="homeai-color-fields"><label>Muestra<input id="homeaiColorPicker" type="color" aria-label="Elegir color personalizado"></label><label>Código HEX<input id="homeaiColorHex" type="text" required pattern="#[0-9a-fA-F]{6}" maxlength="7" placeholder="#e8e0d1" aria-label="Código hexadecimal del color" title="Escribe # seguido de 6 cifras o letras de A a F" spellcheck="false"></label><label>Nombre opcional<input id="homeaiColorName" type="text" maxlength="40" placeholder="Mi color" aria-label="Nombre del color personalizado"></label></div><button type="submit">Aplicar color a la pared</button>';
  document.getElementById('designColors').before(customColor);
  const picker = customColor.querySelector('#homeaiColorPicker');
  const hex = customColor.querySelector('#homeaiColorHex');
  const colorName = customColor.querySelector('#homeaiColorName');
  picker.addEventListener('input', () => {hex.value=picker.value;hex.setCustomValidity('');colorName.value=colorOptions.find(item=>item[0].toLowerCase()===picker.value.toLowerCase())?.[1] || '';});
  hex.addEventListener('input', () => {hex.setCustomValidity('');if(/^#[0-9a-f]{6}$/i.test(hex.value)){picker.value=hex.value;colorName.value=colorOptions.find(item=>item[0].toLowerCase()===hex.value.toLowerCase())?.[1] || '';}});
  customColor.addEventListener('submit', event => {
    event.preventDefault();
    const value=hex.value.trim().toLowerCase();
    if(!/^#[0-9a-f]{6}$/.test(value)){hex.setCustomValidity('Usa el formato #A1B2C3.');hex.reportValidity();return;}
    checkpoint();
    designDraft.wallColor=value;
    designDraft.wallName=colorName.value.trim() || colorOptions.find(item=>item[0].toLowerCase()===value)?.[1] || 'Color personalizado '+value.toUpperCase();
    storeDesignDraft();
    renderDesign(true);
    toast('Color de pared aplicado al borrador.');
  });
  const syncPalettes = () => {
    picker.value = /^#[0-9a-f]{6}$/i.test(designDraft.wallColor) ? designDraft.wallColor : '#e8e0d1';
    hex.value = picker.value;
    colorName.value = designDraft.wallName || '';
    for (const button of section.querySelectorAll('[data-homeai-palette]')) {
      const palette = palettes[Number(button.dataset.homeaiPalette)];
      const selected = designDraft.wallColor.toLowerCase() === colorOptions.find(item=>item[1]===palette.wall)?.[0].toLowerCase() && designDraft.wallName === palette.wall && designDraft.material === palette.floor && designDraft.decor?.textiles === palette.textile && designDraft.decor?.hardware === palette.hardware;
      button.setAttribute('aria-pressed', String(selected));
      button.querySelector('[data-palette-action]').textContent = selected ? '✓ Combinación aplicada' : 'Aplicar combinación →';
    }
  };
  const originalApplyFinish = applyFinish;
  applyFinish = function(...args) {const result = originalApplyFinish.apply(this,args);syncPalettes();return result;};
  const cardSelector = '[data-style],[data-dcolor],[data-wallfinish],[data-floor-name],[data-bath],[data-faucet],.decor-field,.bath-detail,[data-homeai-palette],.pro-config-grid label';
  filterCatalog = function() {
    const query = normalize(document.getElementById('catalogSearch').value.trim());
    const panels = [...document.querySelectorAll('.design-catalog-panel')];
    const counts = {};
    for (const panel of panels) {
      const category = panel.dataset.panel;
      const family = families[category]?.find(group => group[0] === filters[category]);
      let count = 0;
      for (const card of panel.querySelectorAll(cardSelector)) {
        if(card.classList.contains('pro-not-relevant')||(category==='banio'&&roomType(selectedRoom())!=='bath')){card.hidden=true;continue;}
        const options = [...card.querySelectorAll('option')];
        if (options.length) {
          const label = normalize([...card.children].filter(child=>child.tagName!=='SELECT').map(child=>child.textContent).join(' '));
          let matches = 0;
          for (const option of options) {option.hidden = !!query && !label.includes(query) && !normalize(option.textContent).includes(query);if(!option.hidden)matches++;}
          card.hidden = matches === 0;count += matches;
        } else {
          const key = card.dataset.style || card.dataset.floorName;
          const familyName = families[category]?.find(group => group[1].includes(key))?.[0] || '';
          const match = (!family || family[1].includes(key)) && (!query || normalize(card.textContent+' '+familyName).includes(query));
          card.hidden = !match;if(match)count++;
        }
      }
      counts[category] = count;
    }
    const total = Object.values(counts).reduce((sum,count)=>sum+count,0);
    if(query && !counts[activeDesignCategory] && total) setDesignCategory(panels.find(panel=>counts[panel.dataset.panel]).dataset.panel);
    const names = {estilo:'estilos',pared:'opciones de pared y paletas',suelo:'suelos',banio:'opciones de baño',decoracion:'opciones de decoración'};
    document.getElementById('catalogResultCount').textContent = query ? `${total} opciones encontradas` : `${counts[activeDesignCategory] || 0} ${names[activeDesignCategory] || 'opciones'}`;
    document.getElementById('catalogEmpty').hidden = !query || total > 0;
    document.getElementById('clearCatalogSearch').hidden = !query;
    for (const panel of panels) {
      let empty = panel.querySelector('.homeai-filter-empty');
      if (!empty) {
        empty = document.createElement('div');empty.className='homeai-filter-empty';empty.innerHTML='No hay coincidencias con estos filtros.<button type="button">Ver todas las opciones</button>';
        empty.querySelector('button').onclick=()=>{filters[panel.dataset.panel]='';document.getElementById('catalogSearch').value='';panel.querySelectorAll('.catalog-family-filters button').forEach((button,index)=>button.setAttribute('aria-pressed',String(index===0)));filterCatalog();};
        panel.append(empty);
      }
      empty.hidden = counts[panel.dataset.panel] > 0 || total === 0 && !!query;
    }
  };
  document.getElementById('catalogSearch').oninput = filterCatalog;
  filterCatalog();
  syncPalettes();
})();
