# Contrato MQTT y decisiones

## Filtros externos

| Uso | Filtro |
| --- | --- |
| Explorar tranvías | `/hfp/v2/journey/ongoing/vp/tram/#` |
| Línea 1004 | `/hfp/v2/journey/ongoing/vp/+/+/+/1004/#` |
| Línea 1004, sentido 1 | `/hfp/v2/journey/ongoing/vp/+/+/+/1004/1/#` |

`+` selecciona un nivel y `#` el resto de la ruta. La exploración geográfica usó las ramas `60;24/19/85` y `60;24/19/86` para el rectángulo `60.18 ≤ lat < 60.19`, `24.95 ≤ lon < 24.97`. Los topics pueden contener espacios en nombres de parada: separar el JSON por su comienzo, no por el primer espacio.

## Publicación local

| Topic | Contenido y política |
| --- | --- |
| `flota/hsl/<modo>/<oper>/<veh>/posicion` | Coordenadas, velocidad, distancia, parada, viaje y fecha; QoS 0 retenido |
| `flota/hsl/<modo>/<oper>/<veh>/estado` | Línea, sentido, retraso y puertas; QoS 0 retenido |
| `flota/hsl/alarma/puertas` | Puertas abiertas a más de 3 m/s; QoS 1, sin retención |
| `contexto/meteo/actual` | Meteorología actual y fecha de la fuente; retenido |
| `contexto/meteo/prevision` | Nieve acumulada en las dos horas seleccionadas; retenido |
| `decision/plan_invierno` | Activación, validez, motivo y medias; QoS 2 retenido |
| `prediccion/eta/<modo>/<oper>/<veh>` | ETA del modelo y de la base, parada, viaje, versión y fecha |

Velocidad en m/s; distancia en metros; retraso y ETA en segundos. El retraso negativo significa llegar tarde. Nieve actual en cm/h; previsión acumulada en cm. Las fechas se comparan en UTC.

## Calidad y caducidad

El validador exige JSON y VP válidos, origen GPS, coordenadas dentro de la región admitida, velocidad de 0 a 45 m/s y fecha a menos de 30 segundos del reloj. Los fallos salen a cuarentena con motivo.

La regla de invierno compara los últimos diez minutos con el tramo de hace 70 a 60 minutos. Activa cuando hay nieve y `media_antes - media_ahora > 90`. Un contexto caducado o una ventana ausente producen una decisión inválida, no una decisión negativa válida. Un valor nulo o una celda vacía no se convierte en cero.

El servicio ETA exige posición y estado vigentes y un desfase no mayor de cinco segundos. Evalúa todas las predicciones pendientes al llegar el ARS del mismo vehículo, viaje y parada. El mapa descarta las estimaciones caducadas o asociadas a otro recorrido.

## Nodos para consultar el código

La lógica está en `flows/hsl.json`. Buscar los identificadores `f_validar`, `f_normalizar`, `f_meteo`, `f_decidir` y `f_mapa`. La función `f_flux_hdr` lee el token de `INFLUX_TOKEN`; las credenciales del nodo InfluxDB se configuran localmente en el editor.

## Simulación y actuación

| Topic | Contenido |
| --- | --- |
| `sim/hsl/tram/99xx/<veh>/posicion` y `/estado` | Contrato de posición y estado, `run_id`, fecha real, tiempo virtual y factor temporal; retenidos |
| `sim/kpi` | CV del espaciado, retraso, número de vehículos y escenario cada treinta segundos virtuales |
| `sim/residuo/<veh>` | Vehículo real asociado, residuo previo y posterior, fase y ganancia |
| `sim/cmd` | Cambio de escenario o parámetros; incluir `run_id` para aislar el ensayo |
| `sim/evento` | Comandos aceptados, retenciones aplicadas y fin del ensayo |
| `sim/solicitud_retencion` | Petición sintética con retraso del tren, vehículo, operador, espera e identificador |
| `decision/retener/sim/99xx/<veh>` | Orden de espera en la próxima parada, dirigida al ensayo; QoS 1 no retenido |
| `sim/decision_retencion` | Autorización o rechazo con motivo |

La posición simulada se guarda con `src=sim`. El residuo usa `src=real` porque su corrección depende de una observación real; pertenece a `residuo_sim`, no al histórico de posiciones HSL. La primera alineación tiene `fase=alineacion_inicial` y queda fuera de las métricas predictivas. Las consultas reales y el entrenamiento ETA excluyen `src=sim`.
