"""Experimentos deterministas. El tiempo de las tablas es simulado y se conserva la semilla."""
import argparse,csv,json,math,sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from sim_flota import Simulador,Ruta,ruta_sintetica
ap=argparse.ArgumentParser();ap.add_argument('--historico',required=True);a=ap.parse_args()
summary={'semilla':20260930,'paso_s':1,'tipo':'experimentos reproducibles, no episodios operativos observados'}
# S2. Mismo modelo, ruta, inicialización y semilla; cambia únicamente beta.
snow=[];bunch=[]
for beta in [0,.12]:
 for scenario in ['normal','nieve']:
  s=Simulador(Ruta(ruta_sintetica()));s.aplicar_cmd({'beta':beta,'escenario':scenario})
  crossing=None
  for t in range(2400):
   s.paso()
   if s.kpi()['irregularidad']>=.6 and crossing is None:crossing=t+1
  item={'beta':beta,'escenario':scenario,'duracion_sim_s':2400,'irregularidad_final':s.kpi()['irregularidad'],'primer_cv_06_s':crossing,'retraso_final_s':s.kpi()['retraso_medio_s']}
  bunch.append(item)
summary['ruta_escenarios_y_retenciones']='sintética; parámetros nominales, sin asimilación'
summary['retraso_simulado']='respecto al horario interno del modelo, no al horario comercial HSL'
summary['pasajeros_y_nieve']=bunch
# S3. Distribuciones comparables, sin guardar datos pesados en el repositorio.
rd=json.loads((ROOT/'data/ruta-linea-4.json').read_text());cal=rd['calibracion'];route=Ruta(rd['puntos'])
s=Simulador(route,n=4,v_cruce=cal['velocidad_m_s'],dwell=cal['dwell_s'],sep_paradas=cal['paradas_cada_m'])
vel=[]
for t in range(cal['muestra_1hz']):
 s.paso();vel.extend(v.v for v in s.vehs)
counts,_=np.histogram(vel,bins=cal['histograma_real']['limites_m_s'])
summary['histograma_simulado']={'limites_m_s':cal['histograma_real']['limites_m_s'],'frecuencias':counts.tolist(),'n':len(vel),'parado_fraccion':float(np.mean(np.array(vel)<1)),'crucero_p85_m_s':float(np.quantile(np.array(vel)[np.array(vel)>1],.85))}
# S4(a). Elegir una ganancia usando 15 minutos y evaluar los 15 minutos siguientes.
x=pd.read_csv(a.historico,low_memory=False);x['_time']=pd.to_datetime(x['_time'],utc=True,format='mixed');x=x.sort_values('_time')
start=x['_time'].iloc[0];x=x[(x['_time']-start).dt.total_seconds()<=1800]
gains=[.1,.3,.5,.7,1.];gain_rows=[];traces=[]
observations={int((row._time-start).total_seconds()):(row.lat,row.lon) for _,row in x.iterrows()}
# Geometría y tres parámetros permanecen idénticos entre todas las ganancias.
for gain in gains:
 s=Simulador(route,n=1,v_cruce=cal['velocidad_m_s'],dwell=cal['dwell_s'],sep_paradas=cal['paradas_cada_m']);s.ganancia=gain
 v=s.vehs[0];s.asimilar(v,observations[0],k=1,bounds=cal['rangos_sentido']['1'])
 errs=[]
 for t in range(1,1801):
  s.paso()
  if t%60==0 and t in observations:
   result=s.asimilar(v,observations[t],bounds=cal['rangos_sentido']['1'])
   if result:
    row={'ganancia':gain,'t_sim_s':t,'residuo_m':result['residuo_m'],'residuo_posterior_m':result['residuo_posterior_m']};traces.append(row);errs.append(row)
 train=[e['residuo_m'] for e in errs if e['t_sim_s']<=900];test=[e['residuo_m'] for e in errs if e['t_sim_s']>900]
 def stats(values):return {'n':len(values),'mae_m':float(np.mean(np.abs(values))),'rmse_m':float(np.sqrt(np.mean(np.square(values)))),'media_m':float(np.mean(values))}
 gain_rows.append({'ganancia':gain,'seleccion_15min':stats(train),'evaluacion_15min':stats(test)})
selected=min(gain_rows,key=lambda r:r['seleccion_15min']['rmse_m'])['ganancia']
summary['ganancia']={'seleccionada':selected,'referencia':.3,'filas':gain_rows,'desde':start.isoformat(),'hasta':x['_time'].iloc[-1].isoformat(),'descripcion':'reproducción de posiciones reales archivadas; selección con la primera mitad, comparación con la segunda; residuos previos a corregir'}
with (ROOT/'results/ganancia-residuos.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(traces[0]));w.writeheader();w.writerows(traces)
# S5. Contrafactuales pareados, con y sin la retención sobre el mismo estado inicial.
retentions=[];ret_traces=[]
for hold in [0,60,120,240]:
 s=Simulador(Ruta(ruta_sintetica()));applied=None;ended=None;recover=None;stable=0;max_cv=0;initial=None
 for t in range(7200):
  if t==1800:
   initial=s.kpi()['irregularidad']
   if hold:s.retener('00001',hold)
  s.paso();v=s.vehs[0];k=s.kpi()
  if hold and v.retencion_aplicada>0 and applied is None:applied=t+1;ended=v.parado_hasta
  if t>=1800:
   max_cv=max(max_cv,k['irregularidad'])
   if ended is not None and t>=ended:
    stable=stable+1 if k['irregularidad']<=.3 else 0
    if stable>=300 and recover is None:recover=t+1-300-ended
   if t%30==0:ret_traces.append({'retencion_s':hold,'t_sim_s':t+1,'irregularidad':k['irregularidad'],'retraso_medio_s':k['retraso_medio_s']})
 retentions.append({'retencion_s':hold,'irregularidad_antes':initial,'irregularidad_maxima':max_cv,'aplicada_t_sim_s':applied,'fin_parada_t_sim_s':ended,'recuperacion_s':recover,'criterio_recuperacion':'CV ≤ 0,3 durante 300 s consecutivos, desde el fin de la parada retenida','horizonte_despues_orden_s':5400})
summary['retenciones']=retentions
with (ROOT/'results/retencion-trazas.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(ret_traces[0]));w.writeheader();w.writerows(ret_traces)
(ROOT/'results/simulacion-experimentos.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
