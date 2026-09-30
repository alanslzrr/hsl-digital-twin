"""Comprobaciones locales de sintaxis, métricas y contenido publicable."""
from pathlib import Path
import ast
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
errors = []
for name in filter(None, files):
    p = ROOT / name
    if p.stat().st_size > 2_000_000:
        errors.append(f'Archivo mayor de 2 MB: {name}')
    if p.suffix in {'.pkl', '.pickle', '.raw', '.log', '.pid', '.jsonl'} or p.name == '.env':
        errors.append(f'Archivo de ejecución o privado: {name}')
    if p.suffix in {'.jpg', '.jpeg', '.png', '.pdf', '.gif'}:
        continue
    text = p.read_text()
    if re.search(r'gh[pousr]_[A-Za-z0-9]{20,}|lab-hsl-token-\w+-\d+|lab-hsl-20\d\d', text):
        errors.append(f'Posible credencial: {name}')
    if ('/' + 'Users/') in text or ('/' + 'home/') in text:
        errors.append(f'Ruta privada: {name}')
    if p.suffix == '.py':
        ast.parse(text, filename=name)
    if p.suffix == '.json':
        json.loads(text)
report = json.loads((ROOT / 'results/eta-vivo-2h.json').read_text())
assert sum(row['n'] for row in report['cortes']) == report['n'] == 20786
assert report['mae_base_s'] == 29.39 and report['mae_modelo_s'] == 15.89
if errors:
    raise SystemExit('\n'.join(errors))
print(f'Publicación revisada: {len(list(filter(None, files)))} archivos; sintaxis y métricas correctas.')
print('La búsqueda de patrones no sustituye una revisión humana de secretos o capturas.')

cal=json.loads((ROOT / 'results/calibracion-simulacion.json').read_text())
live=json.loads((ROOT / 'results/sincronizacion-simulacion.json').read_text())
experiments=json.loads((ROOT / 'results/simulacion-experimentos.json').read_text())
assert len(live['filas']) == 4
assert all(row['n'] == 30 and row['duracion_observacion_real_s'] >= 1800 and row['alineaciones_excluidas'] == 1 for row in live['filas'])
assert len({row['veh_real'] for row in live['filas']}) == 4
assert sum(cal['histograma_real']['frecuencias']) == cal['histograma_real']['n']
assert sum(experiments['histograma_simulado']['frecuencias']) == experiments['histograma_simulado']['n']
assert [row['retencion_s'] for row in experiments['retenciones']] == [0, 60, 120, 240]
print('Simulación revisada: cuatro parejas, treinta minutos de observación y ensayos pareados coherentes.')
