"""Gemelo cinemático de flota, con experimentos reproducibles y actuación MQTT aislada."""
from __future__ import annotations
import argparse
import bisect
import json
import math
import random
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def haversine(a, b):
    la, lo, lb, lp = map(math.radians, (*a, *b))
    h = math.sin((lb-la)/2)**2 + math.cos(la)*math.cos(lb)*math.sin((lp-lo)/2)**2
    return 12742000 * math.asin(math.sqrt(min(1, max(0, h))))


class Ruta:
    def __init__(self, puntos):
        if len(puntos) < 3:
            raise ValueError("La ruta requiere al menos tres puntos")
        self.p = [tuple(map(float, p)) for p in puntos]
        if any(not (-90 <= a <= 90 and -180 <= b <= 180) for a, b in self.p):
            raise ValueError("Coordenadas inválidas")
        if self.p[-1] != self.p[0]:
            self.p.append(self.p[0])
        self.s = [0.0]
        for a, b in zip(self.p, self.p[1:]):
            self.s.append(self.s[-1]+haversine(a,b))
        self.L = self.s[-1]
        if self.L < 100:
            raise ValueError("La ruta es demasiado corta")
        self._samples = [(m, self.pos(m)) for m in range(0, math.ceil(self.L), 10)]

    def pos(self, m):
        m %= self.L
        i = min(bisect.bisect_right(self.s, m), len(self.s)-1)
        f = (m-self.s[i-1])/max(self.s[i]-self.s[i-1], 1e-9)
        a,b = self.p[i-1],self.p[i]
        return a[0]+f*(b[0]-a[0]), a[1]+f*(b[1]-a[1])

    def rumbo(self, m):
        a,b = self.pos(m),self.pos(m+5)
        return math.degrees(math.atan2((b[1]-a[1])*math.cos(math.radians(a[0])), b[0]-a[0]))%360

    def proyectar(self, p, anterior=None, bounds=None):
        candidates = [(haversine(p,q),m) for m,q in self._samples if bounds is None or bounds[0] <= m <= bounds[1]]
        nearest = min(d for d,m in candidates)
        # En vías de ida y vuelta próximas, conservar la continuidad de la pareja.
        close = [(d,m) for d,m in candidates if d <= nearest+8]
        if anterior is None:
            d,m = min(close)
        else:
            d,m = min(close,key=lambda dm:abs(residuo(dm[1],anterior,self.L)))
        return float(m),d


def residuo(real, previsto, longitud):
    return (real-previsto+longitud/2)%longitud-longitud/2


def ruta_sintetica():
    return [(60.1699,24.9384),(60.1719,24.9415),(60.1745,24.9440),(60.1783,24.9455),
            (60.1830,24.9470),(60.1870,24.9510),(60.1905,24.9530),(60.1930,24.9490),
            (60.1900,24.9420),(60.1860,24.9380),(60.1820,24.9340),(60.1770,24.9330),
            (60.1730,24.9350),(60.1699,24.9384)]


class Vehiculo:
    def __init__(self, vid, m, sim):
        self.id,self.m,self.sim = vid,m,sim
        self.v = 0.0
        self.horario_m = m
        self.horario_acumulado = m
        self.real_acumulado = m
        self.puertas = False
        self.parado_hasta = 0.0
        self.retencion = 0.0
        self.parada_actual = None
        self.prox_parada = sim.siguiente_parada(m)
        self.rng = random.Random(sim.semilla+int(vid)*1009)
        self.retencion_aplicada = 0.0
        self.retencion_terminada = False

    def paso(self, dt, t, gap):
        s=self.sim
        self.horario_acumulado += s.v_media_nominal*dt
        self.horario_m = self.horario_acumulado%s.ruta.L
        if t < self.parado_hasta:
            self.v=0
            return
        if self.puertas:
            s.ultimo_paso[self.parada_actual] = t
            self.puertas=False
            self.retencion_terminada = self.retencion_aplicada > 0
        d = (self.prox_parada-self.m)%s.ruta.L
        move_limit = max(0,gap-12) if len(s.vehs)>1 else s.ruta.L
        if s.corte:
            c0,c1=s.corte
            if c0 <= self.m <= c1:
                move_limit=0
            else:
                dc=(c0-self.m)%s.ruta.L
                move_limit=min(move_limit,max(0,dc-1))
        vobj=min(s.v_cruce*s.factor_velocidad, math.sqrt(2*s.acc*d))
        self.v=min(self.v+s.acc*dt,vobj) if self.v<vobj else max(self.v-s.acc*dt,vobj)
        advance=min(self.v*dt,move_limit)
        if advance >= d or d < 0.5:
            self.real_acumulado += d
            self.m=self.prox_parada
            self.v=0
            self.parada_actual=self.prox_parada
            h=max(0,t-s.ultimo_paso.get(self.prox_parada,t-s.headway))
            dwell=max(1,self.rng.lognormvariate(math.log(s.dwell),s.sigma)+s.beta*h+s.dwell_extra)
            self.retencion_aplicada=self.retencion
            self.parado_hasta=t+dwell+self.retencion
            self.retencion=0
            self.puertas=True
            self.prox_parada=s.siguiente_parada(self.m+0.01)
        else:
            self.real_acumulado += advance
            self.m=(self.m+advance)%s.ruta.L
            self.v=advance/dt
            if advance>0:
                self.parada_actual=None

    def retraso_s(self):
        return -(self.horario_acumulado-self.real_acumulado)/self.sim.v_media_nominal


class Simulador:
    def __init__(self,ruta,n=4,headway=300,v_cruce=11,dwell=18,sep_paradas=450,
                 prefijo="sim/hsl/tram/9999",semilla=20260930):
        if n<1 or n>30 or min(headway,v_cruce,dwell,sep_paradas)<=0 or not prefijo.startswith('sim/'):
            raise ValueError("Parámetros de simulación inválidos")
        self.ruta,self.v_cruce,self.dwell,self.prefijo,self.semilla=ruta,v_cruce,dwell,prefijo,semilla
        self.paradas=[float(m) for m in range(0,math.ceil(ruta.L),round(sep_paradas))]
        self.acc=1.2;self.factor_velocidad=1.;self.dwell_extra=0.;self.corte=None
        self.beta=0.;self.sigma=.35;self.ganancia=1.;self.ultimo_paso={};self.escenario="normal"
        self.v_media_nominal=ruta.L/(1.3*ruta.L/v_cruce+dwell*len(self.paradas))
        self.headway=min(headway,ruta.L/(n*self.v_media_nominal))
        self.vehs=[Vehiculo(f'{i+1:05d}',i*ruta.L/n,self) for i in range(n)]
        self.t=0.;self.lock=threading.RLock()

    def siguiente_parada(self,m):
        i=bisect.bisect_right(self.paradas,m%self.ruta.L)
        return self.paradas[i] if i<len(self.paradas) else self.paradas[0]

    def paso(self,dt=1):
        with self.lock:
            old={v.id:v.m for v in self.vehs}
            for v in self.vehs:
                gap=min(((m-old[v.id])%self.ruta.L for vid,m in old.items() if vid!=v.id),default=self.ruta.L)
                v.paso(dt,self.t,gap)
            self.t+=dt

    def aplicar_cmd(self,cmd):
        if not isinstance(cmd,dict):
            raise ValueError("El comando debe ser un objeto")
        for key,lo,hi in [('factor_velocidad',.05,2),('dwell_extra',-self.dwell+1,600),('beta',0,1),('sigma',0,2),('ganancia',.01,1)]:
            if key in cmd:
                value=cmd[key]
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lo<=value<=hi:
                    raise ValueError(f"Valor inválido para {key}")
        if 'vehiculos' in cmd:
            n=cmd['vehiculos']
            if isinstance(n,bool) or not isinstance(n,int) or not 1<=n<=10 or len(self.vehs)+n>30:
                raise ValueError('Refuerzo inválido')
        with self.lock:
            presets={"normal":(1.,0.,None),"nieve":(.7,8.,None),"evento":(1.,20.,None),
                     "prioridad":(1.1,-3.,None),"corte":(1.,0.,[self.ruta.L*.45,self.ruta.L*.55])}
            if 'escenario' in cmd:
                if cmd['escenario'] not in presets:
                    raise ValueError("Escenario desconocido")
                self.factor_velocidad,self.dwell_extra,self.corte=presets[cmd['escenario']]
                self.escenario=cmd['escenario']
            for key,lo,hi in [('factor_velocidad',.05,2),('dwell_extra',-self.dwell+1,600),('beta',0,1),('sigma',0,2),('ganancia',.01,1)]:
                if key in cmd:
                    value=cmd[key]
                    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lo<=value<=hi:
                        raise ValueError(f"Valor inválido para {key}")
                    setattr(self,key,float(value))
            if 'vehiculos' in cmd:
                n=cmd['vehiculos']
                if isinstance(n,bool) or not isinstance(n,int) or not 1<=n<=10 or len(self.vehs)+n>30:
                    raise ValueError('Refuerzo inválido')
                for _ in range(n):
                    ref=self.vehs[-1];m=(ref.m-self.headway*self.v_media_nominal)%self.ruta.L
                    # Si la inserción coincidiría con otro tranvía, usar el mayor hueco.
                    if any(abs(residuo(m,v.m,self.ruta.L))<24 for v in self.vehs):
                        ordered=sorted(v.m for v in self.vehs)
                        start,gap=max(((m,(ordered[(i+1)%len(ordered)]-m)%self.ruta.L) for i,m in enumerate(ordered)),key=lambda p:p[1])
                        m=(start+gap/2)%self.ruta.L
                    self.vehs.append(Vehiculo(f'{len(self.vehs)+1:05d}',m,self))

    def retener(self,vid,seconds):
        if isinstance(seconds,bool) or not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or not 0<seconds<=600:
            raise ValueError("Retención inválida")
        with self.lock:
            veh=next((v for v in self.vehs if v.id==vid),None)
            if veh is None:
                raise ValueError('Vehículo inexistente')
            veh.retencion=max(veh.retencion,seconds)

    def kpi(self):
        ordered=sorted(v.m for v in self.vehs)
        gaps=[(ordered[(i+1)%len(ordered)]-m)%self.ruta.L for i,m in enumerate(ordered)]
        if len(ordered)==1 or not any(gaps):gaps[-1]=self.ruta.L
        mean=self.ruta.L/len(ordered)
        variance=sum((g-mean)**2 for g in gaps)/len(gaps)
        return {'vehiculos':len(ordered),'headway_medio_s':mean/self.v_media_nominal,
                'irregularidad':math.sqrt(variance)/mean,'retraso_medio_s':sum(v.retraso_s() for v in self.vehs)/len(ordered),
                't_sim_s':self.t,'escenario':self.escenario,'beta':self.beta,'factor_velocidad':self.factor_velocidad,
                'dwell_extra':self.dwell_extra,'ganancia':self.ganancia}

    def asimilar(self,veh,latlon,k=None,bounds=None):
        m,d=self.ruta.proyectar(latlon,veh.m,bounds)
        if d>150:
            return None
        r=residuo(m,veh.m,self.ruta.L);gain=self.ganancia if k is None else k
        veh.real_acumulado += gain*r
        veh.m=(veh.m+gain*r)%self.ruta.L
        veh.v=0;veh.puertas=False;veh.parado_hasta=self.t;veh.parada_actual=None
        veh.prox_parada=self.siguiente_parada(veh.m+0.01)
        return {'residuo_m':r,'residuo_posterior_m':(1-gain)*r,'distancia_ruta_m':d,'ganancia':gain}


def main():
    import paho.mqtt.client as mqtt
    ap=argparse.ArgumentParser(description=__doc__)
    for key,default in [('broker','localhost'),('prefijo','sim/hsl/tram/9999'),('ruta',None),('sync',None),('run-id',None),('registro',None)]:ap.add_argument('--'+key,default=default)
    for key,default in [('puerto',1883),('vehiculos',4),('semilla',20260930)]:ap.add_argument('--'+key,type=int,default=default)
    for key,default in [('headway',300),('velocidad',11),('dwell',18),('paradas-cada',450),('factor-tiempo',1),('beta',0),('sigma',.35),('ganancia',1),('duracion',0),('sync-cada',60)]:ap.add_argument('--'+key,type=float,default=default)
    a=ap.parse_args()
    if a.factor_tiempo<=0 or a.sync_cada<=0:ap.error('Tiempo inválido')
    data=json.loads(Path(a.ruta).read_text()) if a.ruta else None
    route=Ruta(data['puntos'] if data else ruta_sintetica())
    s=Simulador(route,a.vehiculos,a.headway,a.velocidad,a.dwell,a.paradas_cada,a.prefijo,a.semilla)
    s.aplicar_cmd({'beta':a.beta,'sigma':a.sigma,'ganancia':a.ganancia})
    run=a.run_id or 'sim-'+uuid.uuid4().hex[:8]
    log=Path(a.registro).open('a') if a.registro else None
    cli=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id=run)
    real={};pairings={};initialised=set();last_sync=-60;last_kpi=-30;last_publish=-1;last_status={}
    real_lock=threading.RLock()
    def pub(topic,p,retain=False):
        p={**p,'ts':utc(),'run_id':run,'t_sim_s':s.t,'factor_tiempo':a.factor_tiempo}
        cli.publish(topic,json.dumps(p,allow_nan=False),qos=1 if '/residuo/' in topic else 0,retain=retain)
        if log:
            log.write(json.dumps({'topic':topic,'payload':p})+'\n');log.flush()
    def on_connect(c,u,flags,reason,properties):
        if reason.is_failure: return
        c.subscribe('sim/cmd');c.subscribe('decision/retener/sim/#')
        if a.sync:c.subscribe('flota/hsl/#')
    def on_message(c,u,msg):
        try:
            p=json.loads(msg.payload)
            if not isinstance(p,dict):return
            if msg.topic=='sim/cmd':
                if p.get('run_id') and p['run_id'] != run:return
                s.aplicar_cmd(p);pub('sim/evento',{'tipo':'comando','comando':p})
            elif msg.topic.startswith('decision/retener/sim/'):
                if msg.retain or (p.get('run_id') and p['run_id'] != run):return
                parts=msg.topic.split('/')
                if parts[-2]!=a.prefijo.split('/')[-1]:return
                s.retener(parts[-1],p.get('esperar_s'))
                pub('sim/evento',{'tipo':'retencion_aceptada','veh':parts[-1],'esperar_s':p['esperar_s']})
            elif a.sync and msg.topic.startswith('flota/hsl/'):
                parts=msg.topic.split('/')
                if len(parts)!=6:return
                key='/'.join(parts[2:5])
                with real_lock:
                    real.setdefault(key,{})[parts[-1]]=p
        except (ValueError,TypeError,KeyError) as e:
            pub('sim/evento',{'tipo':'rechazado','motivo':str(e),'topic':msg.topic})
    cli.on_connect=on_connect;cli.on_message=on_message
    cli.connect(a.broker,a.puerto);cli.loop_start()
    print(json.dumps({'run_id':run,'longitud_m':route.L,'paradas':len(s.paradas),'modo':'sincronizado' if a.sync else 'libre','factor_tiempo':a.factor_tiempo}),flush=True)
    try:
        while not a.duracion or s.t<a.duracion:
            began=time.monotonic()
            with s.lock:
                s.paso()
                if a.sync and s.t-last_sync>=a.sync_cada:
                    with real_lock:
                        fresh={}
                        for rid,pair in real.items():
                            pos,est=pair.get('posicion',{}),pair.get('estado',{})
                            try:
                                tp=datetime.fromisoformat(pos['ts'].replace('Z','+00:00')).timestamp()
                                te=datetime.fromisoformat(est['ts'].replace('Z','+00:00')).timestamp()
                                if est.get('linea')!=str(int(a.sync)-1000) or not -5<=time.time()-tp<=15 or not -5<=time.time()-te<=15 or abs(tp-te)>5:continue
                                if not all(isinstance(pos.get(k),(float,int)) and not isinstance(pos.get(k),bool) and math.isfinite(pos[k]) for k in ['lat','lon']):continue
                                fresh[rid]={**pos,'dir_observada':str(est.get('dir',''))}
                            except (KeyError,ValueError,TypeError):continue
                    used=set(pairings.values())
                    for v in s.vehs:
                        if v.id not in pairings:
                            candidates=[rid for rid in sorted(fresh) if rid not in used and route.proyectar((fresh[rid]['lat'],fresh[rid]['lon']))[1]<=150]
                            if candidates:pairings[v.id]=candidates[0];used.add(candidates[0])
                        rid=pairings.get(v.id)
                        if rid not in fresh:continue
                        initial = v.id not in initialised
                        bounds = data['calibracion'].get('rangos_sentido',{}).get(fresh[rid]['dir_observada']) if data else None
                        result=s.asimilar(v,(fresh[rid]['lat'],fresh[rid]['lon']),k=1 if initial else None,bounds=bounds)
                        if result:
                            pub('sim/residuo/'+v.id,{**result,'veh_real':rid,'veh':v.id,'src':'real','fase':'alineacion_inicial' if initial else 'prediccion','ts_fuente':fresh[rid]['ts']},True)
                            if initial:
                                v.real_acumulado=v.m;v.horario_acumulado=v.m;v.horario_m=v.m
                            initialised.add(v.id)
                    if initialised:last_sync=s.t
                if s.t-last_publish>=max(1,a.factor_tiempo/5):
                    for v in s.vehs:
                        lat,lon=route.pos(v.m);base=a.prefijo+'/'+v.id
                        pub(base+'/posicion',{'lat':round(lat,6),'lon':round(lon,6),'spd':v.v,'hdg':route.rumbo(v.m),'src':'sim','dist_parada_m':(v.prox_parada-v.m)%route.L},True)
                        pub(base+'/estado',{'linea':'SIM','dir':'1','retraso_s':v.retraso_s(),'puertas':'ABIERTAS' if v.puertas else 'CERRADAS','parada':str(round(v.parada_actual)) if v.parada_actual is not None else None,'src':'sim'},True)
                        status=(v.parada_actual,v.retencion_aplicada,v.puertas)
                        if v.retencion_aplicada and status!=last_status.get(v.id):
                            pub('sim/evento',{'tipo':'retencion_aplicada' if v.puertas else 'retencion_finalizada','veh':v.id,'esperar_s':v.retencion_aplicada})
                            if not v.puertas:v.retencion_aplicada=0
                        last_status[v.id]=status
                    last_publish=s.t
                if s.t-last_kpi>=30:pub('sim/kpi',{**s.kpi(),'oper_sim':a.prefijo.split('/')[-1]},True);last_kpi=s.t
            time.sleep(max(0,1/a.factor_tiempo-(time.monotonic()-began)))
    except KeyboardInterrupt:pass
    finally:
        pub('sim/evento',{'tipo':'fin'});cli.disconnect();cli.loop_stop()
        if log:log.close()

if __name__=='__main__':main()
