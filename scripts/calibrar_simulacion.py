"""Reconstruye una vuelta observada y calibra parámetros sin publicar el histórico bruto."""
import argparse,json,sys,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sim_flota import Ruta,haversine
ap=argparse.ArgumentParser();ap.add_argument('csv');ap.add_argument('--salida',default='data/ruta-linea-4.json');a=ap.parse_args()
x=pd.read_csv(a.csv,dtype={'oper':str,'veh':str,'dir':str,'viaje':str},low_memory=False)
x['_time']=pd.to_datetime(x['_time'],format='mixed',utc=True)
p=x[x.evento.isna()].dropna(subset=['lat','lon','spd','puertas_abiertas','jrn','start_hhmm'])
# Dos viajes consecutivos completos de un mismo vehículo y sentidos opuestos.
jobs=[(6996,1812,'1'),(5357,1853,'2')]
points=[];details=[];journeys=[];closure=[]
for jrn,start,direction in jobs:
 rows=p[(p.veh=='00435')&(p.oper=='0040')&(p.dir==direction)&(p.jrn==jrn)&(p.start_hhmm==start)].sort_values('_time').drop_duplicates(['lat','lon','spd','puertas_abiertas','_time'])
 if len(rows)<100:raise SystemExit('No hay suficientes observaciones del viaje seleccionado')
 q=[]
 for row in rows.itertuples():
  point=(row.lat,row.lon)
  if not q or haversine(q[-1],point)>=25:q.append(point)
 if len(q)<20:raise SystemExit('Geometría insuficiente')
 if points:closure.append(haversine(points[-1],q[0]))
 points+=q
 details.append({'jrn':jrn,'start_hhmm':start,'dir':direction,'desde':rows._time.min().isoformat(),'hasta':rows._time.max().isoformat(),'observaciones':len(rows),'puntos':len(q)})
 journeys.append(rows)
closure.append(haversine(points[-1],points[0]));route=Ruta(points)
selected=pd.concat(journeys).sort_values('_time')
# Una muestra por segundo evita ponderar una posición por el caudal duplicado del broker.
selected=selected.set_index('_time').resample('1s').last().dropna(subset=['lat','lon','spd','puertas_abiertas'])
moving=selected.loc[selected.spd>1,'spd']
durations=[];episode=None;previous=None
for ts,row in selected.iterrows():
 open_doors=row.puertas_abiertas==1
 if previous is not None and (ts-previous).total_seconds()>5:episode=None
 if open_doors and episode is None:episode=ts
 if not open_doors and episode is not None:
  seconds=(ts-episode).total_seconds()
  if 2<=seconds<=180:durations.append(seconds)
  episode=None
 previous=ts
v=float(moving.quantile(.85));dwell=float(np.mean(durations));stop_counts=[]
for info in details:
 trip=f"2026-09-29_{info['start_hhmm']:04d}_{info['jrn']}"
 events=x[(x.evento=='ars')&(x.veh=='00435')&(x.viaje==trip)].dropna(subset=['parada'])
 stop_counts.append(int(events.parada.nunique()))
if not all(n>5 for n in stop_counts):raise SystemExit('Llegadas insuficientes para calibrar separación de paradas')
sep=route.L/sum(stop_counts)
cal={'velocidad_m_s':v,'dwell_s':dwell,'paradas_cada_m':sep,'velocidad_muestras':len(moving),'episodios_puertas_completos':len(durations),'dwell_mediana_s':float(np.median(durations)),'dwell_p85_s':float(np.quantile(durations,.85)),'llegadas_por_sentido':stop_counts,'longitud_m':route.L,'conexiones_terminal_m':closure,'viajes':details,'muestra_1hz':len(selected),'metodo':'posición GPS normalizada y orden cronológico, con reducción espacial de 25 m; vuelta formada por dos sentidos observados','sha256_csv_privado':hashlib.sha256(Path(a.csv).read_bytes()).hexdigest()}
bins=list(range(0,22));counts,_=np.histogram(selected.spd,bins=bins)
cal['rangos_sentido']={'1':[0,route.s[details[0]['puntos']]],'2':[route.s[details[0]['puntos']],route.L]}
cal['histograma_real']={'limites_m_s':bins,'frecuencias':counts.tolist(),'n':len(selected)}
output=Path(a.salida);output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps({'puntos':route.p,'calibracion':cal},ensure_ascii=False,indent=2)+'\n')
Path('results/calibracion-simulacion.json').write_text(json.dumps(cal,ensure_ascii=False,indent=2)+'\n')
selected.reset_index().to_csv(Path(a.csv).with_name('viajes-calibracion-1hz.csv'),index=False)
print(json.dumps(cal,ensure_ascii=False,indent=2))
