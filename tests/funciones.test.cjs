const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const flows = JSON.parse(fs.readFileSync(path.join(__dirname, '../flows/hsl.json')));
function ejecutar(id, msg, estado = {}) {
  const flow = { get: k => estado[k], set: (k, v) => { estado[k] = v; } };
  const node = { status() {}, warn() {}, error() {} };
  return new Function('msg', 'flow', 'node', flows.find(n => n.id === id).func)(msg, flow, node);
}
function vp() { return {VP: {loc:'GPS', lat:60.17, long:24.94, spd:8, tst:new Date().toISOString()}}; }
const invalidos = [null, '', 'no json', [], {}, {VP:null}, {VP:{...vp().VP,loc:'DR'}}, {VP:{...vp().VP,lat:null}}, {VP:{...vp().VP,long:999}}, {VP:{...vp().VP,spd:'abc'}}, {VP:{...vp().VP,spd:46}}, {VP:{...vp().VP,tst:'2000-01-01T00:00:00Z'}}];
invalidos.forEach((payload,i) => test(`HSL: rechazar caso inválido ${i+1}`, () => {
 const r=ejecutar('f_validar',{payload}); assert.equal(r[0],null);assert.ok(r[1].motivo);
}));
test('HSL: aceptar una posición vigente',()=>assert.equal(ejecutar('f_validar',{payload:JSON.stringify(vp())})[1],null));
const meteo = () => ({ts:new Date().toISOString(),nieve_cm_h:0,nieve_2h_cm:0});
function decidir(csv,m=meteo()) { return ejecutar('f_decidir',{payload:csv},{meteo:m})[0]; }
['','ventana,_value\nahora,0','ventana,_value\nahora,\nantes,1','ventana,_value\nahora,   \nantes,1','ventana,_value\nahora,abc\nantes,1'].forEach((csv,i)=>test(`Invierno: invalidar ventana ausente o vacía ${i+1}`,()=>{const r=decidir(csv); assert.equal(r.payload.valida,false);assert.equal(r.payload.activar,false);assert.equal(r.retain,true);}));
test('Invierno: cero numérico es válido',()=>assert.equal(decidir('ventana,_value\nahora,0\nantes,0').payload.valida,true));
test('Invierno: exactamente 90 segundos no activa',()=>assert.equal(decidir('ventana,_value\nahora,0\nantes,90',{...meteo(),nieve_2h_cm:1}).payload.activar,false));
test('Invierno: nieve y más de 90 segundos activan',()=>{const r=decidir('ventana,_value\nahora,0\nantes,91',{...meteo(),nieve_2h_cm:1});assert.equal(r.payload.activar,true);assert.equal(r.qos,2);});
test('Invierno: empeoramiento sin nieve no activa',()=>assert.equal(decidir('ventana,_value\nahora,0\nantes,100').payload.activar,false));
test('Invierno: contexto antiguo invalida',()=>assert.equal(decidir('ventana,_value\nahora,0\nantes,100',{...meteo(),ts:'2000-01-01T00:00:00Z'}).payload.valida,false));
function clima(){return {current:{time:new Date().toISOString(),temperature_2m:14,snowfall:0,precipitation:0,wind_speed_10m:2},hourly:{snowfall:[0,0]}};}
test('Meteo: aceptar cero y publicar contexto',()=>{const r=ejecutar('f_meteo',{payload:clima()});assert.equal(r[0][0].payload.nieve_cm_h,0);assert.equal(r[2],null);});
test('Meteo: un nulo no reemplaza el contexto',()=>{const d=clima();d.current.snowfall=null;const state={meteo:meteo()};const old=state.meteo;assert.ok(ejecutar('f_meteo',{payload:d},state)[2]);assert.equal(state.meteo,old);});
function mapa(override) {
 const state={}; const ts=new Date().toISOString();
 const pos={lat:60.17,lon:24.94,spd:8,viaje:'viaje-1',parada:'123',ts};
 const r=ejecutar('f_mapa',{topic:'flota/hsl/tram/0040/00648/posicion',payload:pos},state);
 if (!override) return r;
 return ejecutar('f_mapa',{topic:'prediccion/eta/tram/0040/00648',payload:{eta_s:20,base_s:25,version:'prueba',viaje:'viaje-1',parada:'123',ts,...override}},state);
}
test('Mapa: posición sin ETA',()=>assert.equal(mapa().payload.ETA_modelo,'sin predicción vigente'));
test('Mapa: ETA válida visible',()=>assert.equal(mapa({}).payload.ETA_modelo,'20 s'));
test('Mapa: otro viaje no reutiliza ETA',()=>assert.equal(mapa({viaje:'viaje-2'}).payload.ETA_modelo,'sin predicción vigente'));
test('Mapa: ETA caducada no se muestra',()=>assert.equal(mapa({ts:'2000-01-01T00:00:00Z'}).payload.ETA_modelo,'sin predicción vigente'));
test('Mapa: ETA negativa no se muestra',()=>assert.equal(mapa({eta_s:-1}).payload.ETA_modelo,'sin predicción vigente'));
