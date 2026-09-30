const parts = String(msg.topic).split('/');
const p = msg.payload;
if (parts.length !== 6 || !p || typeof p !== 'object' || Array.isArray(p)) return null;
const key = parts.slice(2, 5).join('/');
if (parts[5] === 'estado') flow.set('sim_estado_' + key, p);
if (parts[5] === 'posicion') flow.set('sim_pos_' + key, p);
const pos = flow.get('sim_pos_' + key);
const estado = flow.get('sim_estado_' + key) || {};
if (!pos || !Number.isFinite(pos.lat) || !Number.isFinite(pos.lon)) return null;
const edad = (Date.now() - Date.parse(pos.ts)) / 1000;
if (!Number.isFinite(edad) || edad < -5 || edad > 15) return null;
return {payload: {
    name: 'sim_' + parts[3] + '_' + parts[4], lat: pos.lat, lon: pos.lon,
    icon: 'circle', iconColor: 'orange', layer: parts[3] === '9998' ? 'sim sintética' : parts[3] === '9997' ? 'sim prueba de control' : 'sim',
    velocidad: Number(pos.spd || 0).toFixed(1) + ' m/s',
    puertas: estado.puertas || '—', retraso: Number(estado.retraso_s || 0).toFixed(0) + ' s',
    ensayo: String(pos.run_id || ''), tiempo_simulado: Number(pos.t_sim_s || 0).toFixed(0) + ' s'
}};
