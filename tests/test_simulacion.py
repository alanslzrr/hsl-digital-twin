"""Pruebas sin conexión al broker ni datos privados."""
import importlib.util,math,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('sim_flota',Path(__file__).resolve().parents[1]/'src/sim_flota.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class SimulacionTests(unittest.TestCase):
 def setUp(self):self.ruta=mod.Ruta(mod.ruta_sintetica());self.s=mod.Simulador(self.ruta)
 def test_ruta_cerrada(self):self.assertEqual(self.ruta.pos(0),self.ruta.pos(self.ruta.L))
 def test_proyeccion(self):
  m,d=self.ruta.proyectar(self.ruta.pos(500));self.assertLess(d,1);self.assertAlmostEqual(m,500)
 def test_residuo_circular(self):
  self.assertAlmostEqual(mod.residuo(5,995,1000),10);self.assertAlmostEqual(mod.residuo(995,5,1000),-10)
 def test_kpi_equiespaciados(self):self.assertAlmostEqual(self.s.kpi()['irregularidad'],0)
 def test_un_vehiculo(self):
  s=mod.Simulador(self.ruta,n=1);self.assertAlmostEqual(s.kpi()['headway_medio_s'],self.ruta.L/s.v_media_nominal)
 def test_todos_coincidentes(self):
  for v in self.s.vehs:v.m=0
  self.assertAlmostEqual(self.s.kpi()['irregularidad'],math.sqrt(3))
 def test_no_sobrepasar_parada(self):
  v=self.s.vehs[0];v.m=v.prox_parada-.1;v.v=10;v.paso(1,0,1000)
  self.assertTrue(v.puertas);self.assertEqual(v.m,v.parada_actual);self.assertEqual(v.v,0)
 def test_limite_aceleracion(self):
  for _ in range(500):
   old={v.id:v.v for v in self.s.vehs};self.s.paso()
   for v in self.s.vehs:self.assertLessEqual(v.v-old[v.id],self.s.acc+1e-8)
 def test_no_adelantamiento(self):
  v=self.s.vehs[0];initial=v.m;v.v=11;v.paso(1,0,15)
  self.assertLessEqual((v.m-initial)%self.ruta.L,3)
 def test_retraso_no_se_envuelve(self):
  v=self.s.vehs[0];v.horario_acumulado=self.ruta.L*3;v.real_acumulado=0
  self.assertAlmostEqual(v.retraso_s(),-3*self.ruta.L/self.s.v_media_nominal)
 def test_retencion_aplicada_una_vez(self):
  s=mod.Simulador(self.ruta,n=1);v=s.vehs[0];s.retener(v.id,120);v.m=v.prox_parada-.1;v.paso(1,0,self.ruta.L)
  self.assertEqual(v.retencion,0);self.assertEqual(v.retencion_aplicada,120);self.assertGreater(v.parado_hasta,120)
 def test_presets_no_arrastran_corte(self):
  self.s.aplicar_cmd({'escenario':'corte'});self.s.aplicar_cmd({'escenario':'nieve'})
  self.assertIsNone(self.s.corte);self.assertEqual(self.s.factor_velocidad,.7)
 def test_comando_invalido_es_atomico(self):
  self.s.aplicar_cmd({'escenario':'nieve'})
  with self.assertRaises(ValueError):self.s.aplicar_cmd({'escenario':'normal','beta':None})
  self.assertEqual(self.s.escenario,'nieve')
 def test_parametros_invalidos(self):
  for cmd in [{'ganancia':0},{'beta':float('nan')},{'vehiculos':True},{'factor_velocidad':None}]:
   with self.assertRaises(ValueError):self.s.aplicar_cmd(cmd)
 def test_retenciones_invalidas(self):
  for seconds in [None,-1,True,601,float('nan')]:
   with self.assertRaises(ValueError):self.s.retener('00001',seconds)
 def test_asimilacion_actualiza_proxima_parada(self):
  v=self.s.vehs[0];r=self.s.asimilar(v,self.ruta.pos(1000),k=1)
  self.assertLess(abs(r['residuo_posterior_m']),.1);self.assertEqual(v.prox_parada,self.s.siguiente_parada(v.m+.01))
 def test_fuera_de_ruta_no_asimila(self):
  v=self.s.vehs[0];old=v.m;self.assertIsNone(self.s.asimilar(v,(40,-3)));self.assertEqual(old,v.m)
 def test_reproducibilidad(self):
  other=mod.Simulador(self.ruta)
  for _ in range(2400):self.s.paso();other.paso()
  self.assertEqual(self.s.kpi(),other.kpi())
if __name__=='__main__':unittest.main()
