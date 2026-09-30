"""Disparo controlado del tren. Verifica actuación real en el simulador y bloqueo por su KPI."""
import argparse,json,subprocess,sys,time,signal
from pathlib import Path
import paho.mqtt.client as mqtt
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--salida',required=True);a=ap.parse_args();folder=Path(a.salida);folder.mkdir(parents=True,exist_ok=True)
run='bucle-20260930';messages=[];kpi={};cli=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='verificar-bucle-controlado')
def msg(c,u,m):
 try:p=json.loads(m.payload)
 except ValueError:return
 if p.get('run_id')!=run:return
 messages.append({'topic':m.topic,'payload':p})
 if m.topic=='sim/kpi':kpi.clear();kpi.update(p)
cli.on_message=msg;cli.connect('localhost',1883);cli.subscribe('sim/#');cli.loop_start()
child=subprocess.Popen([sys.executable,'-u',str(ROOT/'src/sim_flota.py'),'--run-id',run,'--prefijo','sim/hsl/tram/9997','--factor-tiempo','40','--duracion','3600'],stdout=(folder/'bucle-proceso.log').open('w'),stderr=subprocess.STDOUT)
def wait(predicate,seconds=100):
 end=time.monotonic()+seconds
 while not predicate():
  if child.poll() is not None:raise RuntimeError('El simulador de control se ha detenido')
  if time.monotonic()>end:raise RuntimeError('La condición no se observó dentro del límite')
  time.sleep(.05)
def pub(topic,p):cli.publish(topic,json.dumps(p),qos=1).wait_for_publish()
try:
 wait(lambda:bool(kpi));time.sleep(.2)
 def request(id,seconds):pub('sim/solicitud_retencion',{'run_id':run,'oper':'9997','veh':'00001','esperar_s':seconds,'retraso_tren_s':300,'sintetico':True,'solicitud_id':id})
 request('control-aceptar-60',60)
 wait(lambda:any(m['topic']=='sim/decision_retencion' and m['payload'].get('activar') is True for m in messages))
 wait(lambda:any(m['topic']=='sim/evento' and m['payload'].get('tipo')=='retencion_aplicada' for m in messages))
 pub('sim/cmd',{'run_id':run,'escenario':'corte'})
 wait(lambda:kpi.get('irregularidad',0)>.3)
 cv=kpi['irregularidad'];time.sleep(.2);request('control-bloquear-240',240)
 wait(lambda:any(m['topic']=='sim/decision_retencion' and m['payload'].get('solicitud_id')=='control-bloquear-240' and m['payload'].get('activar') is False for m in messages))
 summary={'run_id':run,'sintetico':True,'contexto_tren':'disparo de prueba con 300 s de retraso, no tren observado','autorizada':next(m['payload'] for m in messages if m['topic']=='sim/decision_retencion' and m['payload'].get('activar') is True),'aplicada':next(m['payload'] for m in messages if m['topic']=='sim/evento' and m['payload'].get('tipo')=='retencion_aplicada'),'irregularidad_al_bloquear':cv,'bloqueada':next(m['payload'] for m in messages if m['topic']=='sim/decision_retencion' and m['payload'].get('solicitud_id')=='control-bloquear-240')}
 (ROOT/'results/bucle-simulacion.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');(folder/'bucle-mqtt.jsonl').write_text(''.join(json.dumps(m)+'\n'for m in messages));print(json.dumps(summary,ensure_ascii=False,indent=2))
finally:
 child.send_signal(signal.SIGINT);child.wait();cli.disconnect();cli.loop_stop()
