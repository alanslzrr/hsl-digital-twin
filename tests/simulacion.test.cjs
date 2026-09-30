const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
function ejecutar(nombre, payload, state = {}, topic = '') {
  const flow = {get: key => state[key], set: (key, value) => {state[key] = value}};
  return new Function('msg', 'flow', fs.readFileSync(path.join(__dirname, '../flows/simulacion', nombre + '.js'), 'utf8'))({payload, topic}, flow);
}
const kpi = (cv = .1) => ({irregularidad: cv, ts: new Date().toISOString(), oper_sim: '9998'});
const request = () => ({run_id: 'prueba', oper: '9998', veh: '00001', esperar_s: 120, retraso_tren_s: 300, sintetico: true, solicitud_id: 'test-1'});
function decision(cv, override = {}) {return ejecutar('retener', {...request(), ...override}, {sim_kpi_prueba: kpi(cv)})}
test('Solo publica decisiones bajo el operador simulado del ensayo', () => assert.equal(decision(.1)[0].topic, 'decision/retener/sim/9998/00001'));
test('CV exactamente 0,3 permite retención', () => assert.ok(decision(.3)[0]));
test('CV por encima de 0,3 bloquea retención', () => assert.equal(decision(.301)[0], null));
test('Sin KPI no se actúa', () => assert.equal(ejecutar('retener', request())[0], null));
test('KPI caducado no se usa', () => assert.equal(ejecutar('retener', request(), {sim_kpi_prueba: {...kpi(), ts: '2000-01-01T00:00:00Z'}})[0], null));
test('Solicitud duplicada no actúa dos veces', () => {const state = {sim_kpi_prueba: kpi()};assert.ok(ejecutar('retener', request(), state)[0]);assert.equal(ejecutar('retener', request(), state)[0], null)});
test('Un operador real no es un actuador permitido', () => assert.equal(decision(.1, {oper: '0040'})[0], null));
test('No confunde nulos con espera numérica', () => assert.equal(decision(.1, {esperar_s: null})[0], null));
test('Un tren con exactamente 240 s no dispara', () => assert.equal(decision(.1, {retraso_tren_s: 240})[0], null));
test('Exige indicar que el disparo es sintético', () => assert.equal(decision(.1, {sintetico: false})[0], null));
test('Un KPI de otro ensayo no autoriza la orden', () => assert.equal(decision(.1, {run_id: 'otro'})[0], null));
test('Posición simulada se etiqueta y no tiene identidad real', () => {const out = ejecutar('guardar', {lat: 60.17, lon:24.94, spd:0, run_id:'prueba'}, {}, 'sim/hsl/tram/9998/00001/posicion');assert.equal(out[0].payload[1].src, 'sim');assert.equal(out[0].payload[1].oper, '9998')});
test('Mapa usa capa y nombre independientes', () => {const out = ejecutar('mapa', {lat:60.17,lon:24.94,spd:0,ts:new Date().toISOString()}, {}, 'sim/hsl/tram/9998/00001/posicion');assert.equal(out.payload.name, 'sim_9998_00001');assert.equal(out.payload.iconColor, 'orange')});
