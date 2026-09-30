const p = msg.payload;
if (!p || typeof p !== 'object' || Array.isArray(p)) return null;
const parts = String(msg.topic).split('/');
const run = String(p.run_id || 'sin_run');
const finite = v => typeof v === 'number' && Number.isFinite(v);
const outputs = [null, null, null, null];
if (parts[0] === 'sim' && parts[1] === 'hsl' && parts.length === 6) {
    const fields = {};
    for (const k of ['lat', 'lon', 'spd', 'hdg', 'dist_parada_m', 'retraso_s', 't_sim_s', 'factor_tiempo']) if (finite(p[k])) fields[k] = p[k];
    if (parts[5] === 'estado') fields.puertas_abiertas = p.puertas === 'ABIERTAS' ? 1 : 0;
    if (!Object.keys(fields).length) return null;
    outputs[0] = { payload: [fields, { src: 'sim', modo: parts[2], oper: parts[3], veh: parts[4], linea: 'SIM', dir: '1', run_id: run }] };
} else if (msg.topic === 'sim/kpi') {
    const fields = {};
    for (const k of ['vehiculos', 'headway_medio_s', 'irregularidad', 'retraso_medio_s', 't_sim_s', 'factor_tiempo', 'beta', 'factor_velocidad', 'dwell_extra', 'ganancia']) if (finite(p[k])) fields[k] = p[k];
    if (!finite(p.irregularidad) || p.irregularidad < 0 || !Number.isFinite(Date.parse(p.ts))) return null;
    flow.set('sim_kpi', p);
    flow.set('sim_kpi_' + run, p);
    outputs[1] = { payload: [fields, { run_id: run, escenario: String(p.escenario), src: 'sim' }] };
} else if (parts[1] === 'residuo') {
    const fields = {};
    for (const k of ['residuo_m', 'residuo_posterior_m', 'distancia_ruta_m', 'ganancia', 't_sim_s']) if (finite(p[k])) fields[k] = p[k];
    if (!finite(p.residuo_m)) return null;
    outputs[2] = { payload: [fields, { run_id: run, veh: parts[2], veh_real: String(p.veh_real), src: String(p.src), fase: String(p.fase || 'prediccion') }] };
} else if (msg.topic === 'sim/evento' || msg.topic === 'sim/decision_retencion') {
    outputs[3] = { payload: [{ valor: 1, t_sim_s: finite(p.t_sim_s) ? p.t_sim_s : 0, detalle: JSON.stringify(p) }, { run_id: run, tipo: String(p.tipo || (p.activar ? 'retencion_autorizada' : 'retencion_bloqueada')), veh: String(p.veh || '') }] };
}
return outputs;
