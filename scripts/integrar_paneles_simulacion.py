"""Paneles de simulación y exclusión explícita de sus muestras en el histórico observado."""
import base64,json,os,re,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
password=os.environ['GRAFANA_PASSWORD'];host=os.getenv('GRAFANA_URL','http://localhost:3000')
headers={'Authorization':'Basic '+base64.b64encode((os.getenv('GRAFANA_USER','lab')+':'+password).encode()).decode(),'Content-Type':'application/json'}
def api(path,data=None):
 req=urllib.request.Request(host+'/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
 return json.load(urllib.request.urlopen(req))
ds=next(d for d in api('datasources') if d['type']=='influxdb');source={'type':'influxdb','uid':ds['uid']}
# Conservar el dashboard existente y sus paneles, sin dejar que sim/ altere sus agregados.
old=api('dashboards/uid/flota-hsl')['dashboard']
for panel in old['panels']:
 for target in panel.get('targets',[]):
  target['query']=re.sub(r'r\._measurement\s*==\s*"vehiculo"(?!\s*and\s*\(not exists r.src)', 'r._measurement == "vehiculo" and (not exists r.src or r.src != "sim")',target.get('query',''))
old['id']=None;api('dashboards/db',{'dashboard':old,'overwrite':True})
(ROOT/'infra/grafana/dashboards/flota-hsl.json').write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n')
def flux(measurement,field,condition=''):
 return f'from(bucket: "flota") |> range(start: v.timeRangeStart, stop: v.timeRangeStop) |> filter(fn: (r) => r._measurement == "{measurement}" and r._field == "{field}" {condition}) |> aggregateWindow(every: v.windowPeriod, fn: last, createEmpty: false)'
def panel(id,title,x,y,w,h,targets,unit='short',type='timeseries'):
 return {'id':id,'title':title,'type':type,'datasource':source,'gridPos':{'x':x,'y':y,'w':w,'h':h},'targets':[{'refId':chr(65+i),'query':q,'datasource':source} for i,q in enumerate(targets)],'fieldConfig':{'defaults':{'unit':unit,'color':{'mode':'palette-classic'},'custom':{'lineWidth':2,'fillOpacity':10,'showPoints':'never'}},'overrides':[]},'options':{'legend':{'displayMode':'list','placement':'bottom'},'tooltip':{'mode':'multi'}}}
scenario='and r.run_id == "escenarios-20260930" and r._time >= time(v: "2026-09-30T14:14:19.278Z")';sync='and r.run_id == "sync-validado-20260930"'
panels=[panel(1,'Escenarios · irregularidad a ×10',0,0,12,9,[flux('kpi_sim','irregularidad',scenario)]),panel(2,'Escenarios · retraso medio simulado',12,0,12,9,[flux('kpi_sim','retraso_medio_s',scenario)],'s'),panel(3,'Sincronización real · residuo antes de corregir',0,9,24,11,[flux('residuo_sim','residuo_m',sync+' and r.fase == "prediccion"')],'lengthm')]
for item in panels[:2]:
 item['targets'][0]['query']=item['targets'][0]['query'].replace(' |> aggregateWindow', ' |> group(columns:["_field","run_id","src"]) |> aggregateWindow')
 item['fieldConfig']['defaults']['displayName']='CV' if item['id']==1 else 'Retraso medio'
panels[2]['fieldConfig']['defaults']['displayName']='${__field.labels.veh_real}'
q='''from(bucket:"flota") |> range(start: -24h) |> filter(fn:(r)=>r._measurement == "histograma_sim" and r._field == "porcentaje") |> group(columns:["intervalo","origen"]) |> last() |> group(columns:[]) |> pivot(rowKey:["intervalo"],columnKey:["origen"],valueColumn:"_value") |> keep(columns:["intervalo","real","sim"]) |> sort(columns:["intervalo"])'''
hist=panel(4,'Velocidades · histórico real y modelo calibrado',0,20,14,10,[q],'percent','barchart');hist['targets'][0]['format']='table';hist['options']={'orientation':'vertical','xField':'intervalo','stacking':'none','showValue':'never','legend':{'displayMode':'list','placement':'bottom'},'tooltip':{'mode':'multi'},'xTickLabelRotation':-45};panels.append(hist)
proof='''from(bucket:"flota") |> range(start:v.timeRangeStart,stop:v.timeRangeStop) |> filter(fn:(r)=>r._measurement == "evento_sim" and r._field == "detalle" and r.run_id == "bucle-20260930") |> group(columns:[]) |> keep(columns:["_time","tipo","_value"]) |> sort(columns:["_time"]) |> rename(columns:{_value:"Decisión y motivo"})'''
panels.append(panel(5,'Bucle cerrado · prueba controlada del tren',14,20,10,10,[proof],type='table'))
annotation={'name':'Cambios de escenario','filter':{'exclude':False,'ids':[1,2]},'enable':True,'hide':False,'iconColor':'#ff9f40','datasource':source,'target':{'refId':'Anno','query':'''from(bucket:"flota") |> range(start:v.timeRangeStart,stop:v.timeRangeStop) |> filter(fn:(r)=>r._measurement == "evento_sim" and r._field == "detalle" and r.run_id == "escenarios-20260930" and r._time >= time(v: "2026-09-30T14:14:19.278Z") and r.tipo == "comando") |> rename(columns:{_value:"text",tipo:"tags"}) |> keep(columns:["_time","text","tags"])'''}}
dashboard={'id':None,'uid':'flota-simulacion','title':'Flota HSL · Simulación','tags':['HSL','simulación'],'timezone':'Europe/Madrid','schemaVersion':39,'version':1,'editable':True,'refresh':'10s','time':{'from':'2026-09-30T14:14:00Z','to':'2026-09-30T14:46:00Z'},'panels':panels,'annotations':{'list':[annotation]},'templating':{'list':[]}}
response=api('dashboards/db',{'dashboard':dashboard,'overwrite':True});print(response['status'],response['url'])
(ROOT/'infra/grafana/dashboards/flota-simulacion.json').write_text(json.dumps(dashboard,ensure_ascii=False,indent=2)+'\n')
