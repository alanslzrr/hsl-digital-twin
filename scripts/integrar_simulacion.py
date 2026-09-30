"""Añade la simulación al flujo existente conservando configuración y credenciales locales."""
import json,re,urllib.request,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
url='http://localhost:1880/flows'
flows=json.load(urllib.request.urlopen(url))
Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/flows-antes-simulacion.json').write_text(json.dumps(flows,indent=2))
flows=[n for n in flows if not n['id'].startswith('sim_')]
tab='sim_tab';flows.append({'id':tab,'type':'tab','label':'Simulación · escenarios y control','disabled':False,'info':'Flota sintética y sincronizada. Las retenciones solo actúan sobre sim/.'})
def node(id,type,name,x,y,wires=None,**extra):
 n={'id':'sim_'+id,'z':tab,'type':type,'name':name,'x':x,'y':y,'wires':wires or [],**extra};flows.append(n);return n
node('in','mqtt in','Flota simulada',140,80,[['sim_guardar','sim_mapa']],topic='sim/hsl/#',qos='0',datatype='json',broker='cfg_local',nl=False,rap=True,rh=0,inputs=0)
for id,topic,y in [('kpi','sim/kpi',150),('res','sim/residuo/+',220),('event','sim/evento',290),('decision','sim/decision_retencion',330)]:
 node('in_'+id,'mqtt in',topic,140,y,[['sim_guardar']],topic=topic,qos='0',datatype='json',broker='cfg_local',nl=False,rap=True,rh=0,inputs=0)
node('guardar','function','Guardar telemetría simulada',430,180,[["sim_out_veh"],["sim_out_kpi"],["sim_out_res"],["sim_out_event"]],func=(ROOT/'flows/simulacion/guardar.js').read_text(),outputs=4,noerr=0,initialize='',finalize='',libs=[])
for id,measurement,y in [('veh','vehiculo',70),('kpi','kpi_sim',140),('res','residuo_sim',210),('event','evento_sim',280)]:
 node('out_'+id,'influxdb out',measurement,760,y,[[]],influxdb='cfg_influx',measurement=measurement,precision='',retentionPolicy='',database='database',precisionV18FluxV20='ms',retentionPolicyV18Flux='',org='lab',bucket='flota')
node('mapa','function','Mapa · capa naranja',430,360,[['sim_link_out']],func=(ROOT/'flows/simulacion/mapa.js').read_text(),outputs=1,noerr=0,initialize='',finalize='',libs=[])
node('link_out','link out','Mapa compartido',700,360,[],mode='link',links=['sim_link_in'])
n=node('link_in','link in','Flota simulada',1020,220,[['worldmap']],links=['sim_link_out']);n['z']='tab_paso5'
node('sol','mqtt in','Prueba de conexión del tren',170,470,[['sim_retener']],topic='sim/solicitud_retencion',qos='1',datatype='json',broker='cfg_local',nl=False,rap=False,rh=2,inputs=0)
node('retener','function','Retener solo si CV ≤ 0,3',440,470,[['sim_mqtt_cmd'],['sim_mqtt_result']],func=(ROOT/'flows/simulacion/retener.js').read_text(),outputs=2,noerr=0,initialize='',finalize='',libs=[])
for id,y in [('cmd',450),('result',510)]:node('mqtt_'+id,'mqtt out','Decisión simulada' if id=='cmd' else 'Motivo de decisión',760,y,[],topic='',qos='',retain='',respTopic='',contentType='',userProps='',correl='',expiry='',broker='cfg_local')
# Ninguna medida simulada debe entrar en consultas del transporte observado.
for n in flows:
 for key in ['func','payload']:
  if isinstance(n.get(key),str) and not n['id'].startswith('sim_'):
   n[key]=re.sub(r'r\._measurement\s*==\s*"vehiculo"(?!\s*and\s*\(not exists r.src)', 'r._measurement == "vehiculo" and (not exists r.src or r.src != "sim")', n[key])
 if n['id']=='f_normalizar':
  n['func']=n['func'].replace('const tags = { modo, oper, veh,','const tags = { src: "real", modo, oper, veh,')
route=json.loads((ROOT/'data/ruta-linea-4.json').read_text())['puntos']
node('route_inject','inject','Trazado GPS observado',190,590,[['sim_route']],props=[{'p':'payload'}],repeat='30',crontab='',once=True,onceDelay=3,topic='',payload='',payloadType='date')
node('route','function','Ruta real de dos sentidos',470,590,[['sim_link_out']],func='return {payload:{name:"ruta_linea_4", layer:"ruta real", line:'+json.dumps(route)+', color:"#2676c9", weight:3, opacity:0.65}};',outputs=1,noerr=0,initialize='',finalize='',libs=[])
data=json.dumps(flows).encode();req=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json','Node-RED-Deployment-Type':'flows'},method='POST')
print('Despliegue Node-RED',urllib.request.urlopen(req).status,'nodos',len(flows))
# El flujo público omite valores de autenticación, pero conserva los IDs de configuración.
clean=json.loads(json.dumps(flows))
for n in clean:
 for key in ['password','token','credentials','headers']:n.pop(key,None)
 for key in ['func','payload']:
  if isinstance(n.get(key),str):n[key]=re.sub(r'lab-hsl-token[^\s"\']*','${INFLUX_TOKEN}',n[key])
(ROOT/'flows/hsl.json').write_text(json.dumps(clean,ensure_ascii=False,indent=2)+'\n')
