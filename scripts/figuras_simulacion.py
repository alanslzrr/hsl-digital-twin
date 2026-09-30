"""Figuras vectoriales a partir de las tablas del experimento, con ejes y unidades explícitos."""
import csv,json,html,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/diagrams';OUT.mkdir(exist_ok=True)
COLORS=['#1764b0','#e47b21','#397952','#97499e','#6c7681']
def esc(x):return html.escape(str(x))
def chart(name,title,xlabel,ylabel,series,xmax,ymin,ymax,markers=()):
 w,h=1280,700;left,right,top,bottom=110,1230,100,560
 sx=lambda x:left+x/xmax*(right-left);sy=lambda y:bottom-(y-ymin)/(ymax-ymin)*(bottom-top)
 parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><rect width="{w}" height="{h}" fill="white"/><g font-family="Arial,sans-serif" fill="#162333"><text x="110" y="48" font-size="27" font-weight="700">{esc(title)}</text>']
 for i in range(6):
  y=ymin+(ymax-ymin)*i/5;yy=sy(y);parts.append(f'<path d="M110 {yy}H1230" stroke="#e1e7ee"/><text x="95" y="{yy+5}" text-anchor="end" font-size="16">{y:.1f}</text>')
 for i in range(7):
  x=xmax*i/6;xx=sx(x);parts.append(f'<text x="{xx}" y="589" text-anchor="middle" font-size="16">{x:.0f}</text>')
 for x,label in markers:
  xx=sx(x);parts.append(f'<path d="M{xx} 100V560" stroke="#a7aeb8" stroke-dasharray="5 6"/><text x="{xx+7}" y="90" font-size="14">{esc(label)}</text>')
 for i,(label,values) in enumerate(series):
  color=COLORS[i%len(COLORS)];p=' '.join(f'{sx(x):.2f},{sy(y):.2f}'for x,y in values);parts.append(f'<polyline points="{p}" fill="none" stroke="{color}" stroke-width="2.4"/><path d="M{110+i*245} 653h25" stroke="{color}" stroke-width="4"/><text x="{145+i*245}" y="659" font-size="16">{esc(label)}</text>')
 parts.extend([f'<text x="670" y="620" text-anchor="middle" font-size="18">{esc(xlabel)}</text>',f'<text x="28" y="320" transform="rotate(-90 28 320)" text-anchor="middle" font-size="18">{esc(ylabel)}</text>','</g></svg>']);(OUT/(name+'.svg')).write_text(''.join(parts))
sc=json.load(open(ROOT/'results/escenarios-simulacion.json'));rows=list(csv.DictReader(open(ROOT/'results/escenarios-trazas.csv')))
markers=[(c['t_sim_s']/60,['Nieve','Nominal','Corte','Nominal','+2 vehículos'][i])for i,c in enumerate(sc['comandos'])]
chart('sim-escenarios','Irregularidad del espaciado en el ensayo MQTT','Tiempo simulado (min)','Coeficiente de variación', [('Flota simulada',[(float(r['t_sim_s'])/60,float(r['irregularidad']))for r in rows])],181,0,1.8,markers)
ret=list(csv.DictReader(open(ROOT/'results/retencion-trazas.csv')))
series=[(f'Retención {hold} s',[(float(r['t_sim_s'])/60-30,float(r['irregularidad']))for r in ret if int(r['retencion_s'])==hold])for hold in [0,60,120,240]]
chart('sim-retenciones','Coste de la retención frente al mismo ensayo sin retener','Minutos simulados desde la orden','Coeficiente de variación',series,90,0,1)
gain=list(csv.DictReader(open(ROOT/'results/ganancia-residuos.csv')))
series=[(f'Ganancia {g}',[(float(r['t_sim_s'])/60,float(r['residuo_m']))for r in gain if float(r['ganancia'])==g])for g in [.3,1]]
chart('sim-ganancia','Comparación de ganancias sobre posiciones reales archivadas','Tiempo del registro observado (min)','Residuo previo a corregir (m)',series,30,-800,400,[(15,'Fin de selección')])
cal=json.load(open(ROOT/'results/calibracion-simulacion.json'));exp=json.load(open(ROOT/'results/simulacion-experimentos.json'))
parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="700" viewBox="0 0 1280 700"><rect width="1280" height="700" fill="white"/><g font-family="Arial,sans-serif" fill="#162333"><text x="110" y="48" font-size="27" font-weight="700">Distribución normalizada de velocidades</text>']
for i in range(7):
 y=560-i*70;parts.append(f'<path d="M110 {y}H1230" stroke="#e1e7ee"/><text x="95" y="{y+5}" text-anchor="end" font-size="16">{i*10}%</text>')
for origin,hist,color,off in [('Real',cal['histograma_real'],COLORS[0],0),('Simulada',exp['histograma_simulado'],COLORS[1],20)]:
 for i,n in enumerate(hist['frecuencias'][:14]):
  height=n/hist['n']*100*7;parts.append(f'<rect x="{130+i*76+off}" y="{560-height}" width="19" height="{height}" fill="{color}"/>')
for i in range(14):parts.append(f'<text x="{150+i*76}" y="590" text-anchor="middle" font-size="15">{i}–{i+1}</text>')
parts.append('<text x="670" y="630" text-anchor="middle" font-size="18">Intervalo de velocidad (m/s)</text><path d="M430 660h25" stroke="#1764b0" stroke-width="6"/><text x="470" y="666" font-size="18">Observada</text><path d="M720 660h25" stroke="#e47b21" stroke-width="6"/><text x="760" y="666" font-size="18">Simulada</text></g></svg>');(OUT/'sim-velocidades.svg').write_text(''.join(parts))
# Diagrama con la misma paleta editorial y conectores del resto de la memoria.
parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="480" viewBox="0 0 1280 480"><defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto"><path d="M0 0L8 4L0 8" fill="none" stroke="#1764b0"/></marker></defs><rect width="1280" height="480" fill="white"/><g font-family="Arial,sans-serif" fill="#162333"><text x="50" y="45" font-size="27" font-weight="700">El bucle actúa sobre la flota simulada, nunca sobre HSL</text>']
nodes=[(50,160,'Flota real','GPS fresco y dirección'),(350,160,'Gemelo cinemático','Ruta y parámetros calibrados'),(650,160,'Mapa y medidas','Irregularidad y residuos'),(950,160,'Regla de retención','Actuar solo con CV ≤ 0,3')]
for i,(x,y,title,sub)in enumerate(nodes):
 parts.append(f'<rect x="{x}" y="{y}" width="250" height="100" rx="10" fill="#f1f6fb" stroke="#b5c9dc"/><text x="{x+20}" y="{y+40}" font-size="21" font-weight="700">{esc(title)}</text><text x="{x+20}" y="{y+73}" font-size="16">{esc(sub)}</text>')
 if i<3:parts.append(f'<path d="M{x+250} {y+50}H{x+295}" fill="none" stroke="#1764b0" stroke-width="2" marker-end="url(#arrow)"/>')
parts.append('<path d="M1075 260V345H475V263" fill="none" stroke="#1764b0" stroke-width="2" stroke-dasharray="7 5" marker-end="url(#arrow)"/><text x="650" y="329" font-size="17">Orden de espera en la próxima parada</text><text x="50" y="410" font-size="18">Escenarios controlados cambian velocidad, paradas, cortes y refuerzos.</text><text x="50" y="440" font-size="16" fill="#617083">Los ensayos sin sincronización permiten observar el efecto de la decisión sin copiar la realidad.</text></g></svg>');(OUT/'simulacion.svg').write_text(''.join(parts))
print('Cinco figuras vectoriales generadas desde los resultados')
