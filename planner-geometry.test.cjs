const assert=require('node:assert/strict');
const G=require('./planner-geometry.js');
const a={id:'a',name:'Sofá',x:0,y:0,w:100,d:50,rotation:0};
assert.deepEqual(G.size({...a,rotation:90}),{w:50,d:100});
assert.deepEqual(G.size({...a,rotation:270}),{w:50,d:100});
assert.deepEqual(G.size({...a,rotation:180}),{w:100,d:50});
assert.equal(G.overlaps(a,{...a,x:100}),false,'edge contact is not overlap');
assert.equal(G.overlaps(a,{...a,x:99}),true);
assert.equal(G.outside(a,{w:100,d:50}),false);
assert.equal(G.outside({...a,x:-1},{w:100,d:50}),true);
assert.equal(G.outside({...a,rotation:90},{w:100,d:50}),true);
assert.deepEqual(G.firstSpace(a,[a],{w:200,d:100}),{x:100,y:0});
assert.deepEqual(G.firstSpace(a,[a],{w:100,d:100}),{x:0,y:50});
assert.deepEqual(G.firstSpace(a,[a],{w:100,d:50}),{x:0,y:0},'no fit leaves visible overlap to fix');
assert.equal(G.issues([a,{...a,id:'b',layer:'rug'}],{w:200,d:200}).length,0);
assert.equal(G.issues([a,{...a,id:'b',x:20}],{w:200,d:200}).length,1);
assert.equal(G.issues([{...a,x:-1}],{w:200,d:200})[0].type,'outside');
assert.equal(G.valid(Infinity),false);assert.equal(G.valid(0),false);assert.equal(G.valid('250'),true);

/* Digital Home Twin: ligar paredes a habitaciones (computeRoomRegions/matchRoomsToRegions) */
const bounds={minX:0,maxX:200,minY:0,maxY:100};
const segs=[{x1:0,y1:0,x2:200,y2:0,axis:'h'},{x1:0,y1:100,x2:200,y2:100,axis:'h'},{x1:0,y1:0,x2:0,y2:100,axis:'v'},{x1:200,y1:0,x2:200,y2:100,axis:'v'},{x1:100,y1:0,x2:100,y2:100,axis:'v'}];
const regions=G.computeRoomRegions(segs,bounds,{cols:20,rows:10,marginCells:1});
assert.equal(regions.length,2,'un muro divisor produce dos regiones libres');
assert.ok(regions[0].maxX<=100,'la región mayor queda a la izquierda del muro divisor');
assert.ok(regions[1].minX>=100,'la región menor queda a la derecha del muro divisor');
assert.equal(G.computeRoomRegions([],{minX:0,maxX:0,minY:0,maxY:0}).length,0,'sin límites válidos no hay regiones');
const roomsMeasured=[{name:'A',w:70,d:60,verified:true},{name:'B',w:60,d:60,verified:true}];
const matches=G.matchRoomsToRegions(roomsMeasured,regions,1);
assert.equal(matches[0].region,regions[0],'la habitación más grande liga con la región más grande');
assert.equal(matches[1].region,regions[1],'la habitación más pequeña liga con la región más pequeña');
assert.ok(matches[0].confidence>0.99&&matches[1].confidence>0.99,'coincidencia casi exacta de área da confianza alta');
const matchesUnmeasured=G.matchRoomsToRegions([{name:'C',w:'',d:''}],regions,1);
assert.equal(matchesUnmeasured[0].confidence,.25,'sin medidas confirmadas, el enlace es de baja confianza');
assert.ok(regions.includes(matchesUnmeasured[0].region));

/* Digital Home Twin: detección de huecos (detectOpenings) */
const wallLine=[
  {x1:0,y1:0,x2:100,y2:0,axis:'h'},{x1:180,y1:0,x2:300,y2:0,axis:'h'}, // hueco de 80px -> 0.8m, plausible
  {x1:0,y1:50,x2:100,y2:50,axis:'h'},{x1:105,y1:50,x2:300,y2:50,axis:'h'}, // hueco de 5px -> 0.05m, ruido
  {x1:0,y1:100,x2:100,y2:100,axis:'h'},{x1:300,y1:100,x2:400,y2:100,axis:'h'}, // hueco de 200px -> 2m, demasiado grande
];
const openings=G.detectOpenings(wallLine,{pxPerMeter:100});
assert.equal(openings.length,1,'solo el hueco de anchura plausible se detecta como apertura');
assert.equal(openings[0].widthM,0.8);
assert.equal(openings[0].x1,100);assert.equal(openings[0].x2,180);assert.equal(openings[0].y1,0);
assert.ok(openings[0].confidence>0.6,'0.8m es un ancho de puerta plausible -> confianza razonablemente alta');
assert.equal(openings[0].kind,'opening','no se etiqueta puerta ni ventana sin poder distinguirlas de verdad');
assert.equal(G.detectOpenings([],{pxPerMeter:100}).length,0);

console.log('Planner geometry: 30 assertions passed.');
