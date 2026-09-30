"""Ensayo MQTT acelerado con cambios a los 1800 segundos simulados, nunca fechas inventadas."""
import argparse,json,subprocess,sys,time
from pathlib import Path
import paho.mqtt.client as mqtt
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--salida',required=True);ap.add_argument('--factor',type=float,default=10);a=ap.parse_args()
folder=Path(a.salida);folder.mkdir(parents=True,exist_ok=True)
run='escenarios-20260930';seen={'t':0};changes=[]
cli=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='ensayo-escenarios-control')
def msg(c,u,m):
 try:p=json.loads(m.payload)
 except ValueError:return
 if p.get('run_id')==run:seen['t']=p.get('t_sim_s',0)
cli.on_message=msg;cli.connect('localhost',1883);cli.subscribe('sim/kpi');cli.loop_start()
child=subprocess.Popen([sys.executable,'-u',str(ROOT/'src/sim_flota.py'),'--factor-tiempo',str(a.factor),'--prefijo','sim/hsl/tram/9998','--run-id',run,'--duracion','10860','--registro',str(folder/'escenarios-mqtt.jsonl')],stdout=(folder/'escenarios-proceso.log').open('w'),stderr=subprocess.STDOUT)
plan=[(1800,{'escenario':'nieve'}),(3600,{'escenario':'normal'}),(5400,{'escenario':'corte'}),(7200,{'escenario':'normal'}),(9000,{'vehiculos':2})]
start=time.monotonic()
try:
 for threshold,cmd in plan:
  while seen['t']<threshold:
   if child.poll() is not None:raise RuntimeError('El simulador finalizó antes del comando')
   if time.monotonic()-start>12000/a.factor:raise RuntimeError('Tiempo máximo del ensayo superado')
   time.sleep(.2)
  command={**cmd,'run_id':run}
  cli.publish('sim/cmd',json.dumps(command),qos=1).wait_for_publish()
  changes.append({'t_sim_s_kpi':seen['t'],'comando':cmd,'instante_real':time.time()})
  (folder/'comandos-escenarios.json').write_text(json.dumps(changes,indent=2))
  print('Comando',threshold,cmd,flush=True)
 child.wait()
finally:
 if child.poll() is None:child.terminate();child.wait()
 cli.disconnect();cli.loop_stop()
