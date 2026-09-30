"""Resume los registros propios del ensayo, sin mezclar preliminares ni fuentes reales y simuladas."""
import argparse,csv,json,hashlib,math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--artefactos',required=True);ap.add_argument('--exigir-30min',action='store_true');a=ap.parse_args();folder=Path(a.artefactos)
def load(name):return [json.loads(l) for l in (folder/name).read_text().splitlines() if l.strip()]
raw=load('escenarios-mqtt.jsonl');kpis=[r['payload'] for r in raw if r['topic']=='sim/kpi']
commands=[r['payload'] for r in raw if r['topic']=='sim/evento' and r['payload'].get('tipo')=='comando']
phases=[('Nominal',0)]+[(name,c['t_sim_s']) for name,c in zip(['Nieve','Nominal tras nieve','Corte','Nominal tras corte','Refuerzo +2'],commands)]
rows=[]
for i,(name,start) in enumerate(phases):
 end=phases[i+1][1] if i+1<len(phases) else start+1800
 near=min([k for k in kpis if start<=k['t_sim_s']<=end],key=lambda k:abs(k['t_sim_s']-(start+1800)))
 rows.append({'fase':name,'inicio_t_sim_s':start,'medicion_t_sim_s':near['t_sim_s'],'irregularidad':near['irregularidad'],'retraso_medio_s':near['retraso_medio_s'],'vehiculos':near['vehiculos'],'ts':near['ts']})
scenario={'run_id':'escenarios-20260930','factor_tiempo':10,'duracion_fase_sim_s':1800,'duracion_fase_real_aprox_s':180,'desde':kpis[0]['ts'],'hasta':kpis[-1]['ts'],'filas':rows,'comandos':commands,'sha256_registro':hashlib.sha256((folder/'escenarios-mqtt.jsonl').read_bytes()).hexdigest()}
(ROOT/'results/escenarios-simulacion.json').write_text(json.dumps(scenario,ensure_ascii=False,indent=2)+'\n')
with (ROOT/'results/escenarios-trazas.csv').open('w') as f:
 keys=['t_sim_s','irregularidad','retraso_medio_s','escenario','vehiculos','ts'];w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({key:k[key]for key in keys}for k in kpis)
observaciones=[r['payload'] for r in load('sync-real.jsonl') if '/residuo/' in r['topic']]
res=[r for r in observaciones if r.get('fase')=='prediccion']
by=defaultdict(list)
for r in res:by[r['veh']].append(r)
summary=[]
for veh,values in sorted(by.items()):
 values.sort(key=lambda r:r['ts']);y=[r['residuo_m'] for r in values]
 span=(datetime.fromisoformat(values[-1]['ts'].replace('Z','+00:00'))-datetime.fromisoformat(values[0]['ts'].replace('Z','+00:00'))).total_seconds()
 initial=min(r['ts'] for r in observaciones if r['veh']==veh)
 observation_span=(datetime.fromisoformat(values[-1]['ts'].replace('Z','+00:00'))-datetime.fromisoformat(initial.replace('Z','+00:00'))).total_seconds()
 summary.append({'inicio_observacion':initial,'duracion_observacion_real_s':observation_span,'alineaciones_excluidas':sum(r.get('fase')!='prediccion' for r in observaciones if r['veh']==veh),'veh':veh,'veh_real':values[0]['veh_real'],'n':len(y),'desde':values[0]['ts'],'hasta':values[-1]['ts'],'duracion_real_s':span,'media_m':sum(y)/len(y),'mae_m':sum(abs(v)for v in y)/len(y),'rmse_m':math.sqrt(sum(v*v for v in y)/len(y)),'min_m':min(y),'max_m':max(y),'ganancia':values[0]['ganancia']})
if a.exigir_30min and (len(summary)!=4 or min(r['duracion_observacion_real_s']for r in summary)<1800):raise SystemExit('Todavía no hay treinta minutos reales de observación por cada pareja')
live={'run_id':'sync-validado-20260930','metodo':'observaciones reales frescas de la línea 1004; parejas estables; primera alineación excluida; residuos previos a corregir; sin compresión de tiempo','filas':summary,'sha256_registro':hashlib.sha256((folder/'sync-real.jsonl').read_bytes()).hexdigest()}
(ROOT/'results/sincronizacion-simulacion.json').write_text(json.dumps(live,ensure_ascii=False,indent=2)+'\n')
with (ROOT/'results/sincronizacion-trazas.csv').open('w') as f:
 keys=['ts','veh','veh_real','t_sim_s','residuo_m','residuo_posterior_m','distancia_ruta_m','ganancia'];w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({key:r[key]for key in keys}for r in res)
print('Escenarios',len(rows),'residuos por pareja',[(r['veh'],r['n'],round(r['duracion_real_s']))for r in summary])
