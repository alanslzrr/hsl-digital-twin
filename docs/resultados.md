# Resultados de las sesiones

## Comparación ETA cerrada

La sesión del 29 de septiembre de 2026 va de 13:51:58.166 a 15:54:04.165 UTC y corresponde al evaluador `v2` y al modelo en memoria `piloto-1`. Cada ARS puntúa todas las predicciones pendientes del mismo vehículo, viaje y parada.

| Horizonte | Estado | Casos | MAE base | MAE modelo |
| --- | --- | ---: | ---: | ---: |
| < 30 s | En marcha | 9 777 | 3,98 s | 11,62 s |
| < 30 s | Parado | 271 | 58,11 s | 26,86 s |
| 30–60 s | En marcha | 5 391 | 14,38 s | 11,58 s |
| 30–60 s | Parado | 839 | 107,27 s | 9,83 s |
| > 60 s | En marcha | 3 453 | 39,81 s | 29,54 s |
| > 60 s | Parado | 1 055 | 238,09 s | 34,88 s |
| Global | Todos | 20 786 | 29,39 s | 15,89 s |

Los casos son predicciones, no viajes independientes. La ventaja global del modelo depende especialmente de los vehículos parados; la base gana en el grupo más numeroso. Los resultados están en [`eta-vivo-2h.json`](../results/eta-vivo-2h.json).

`piloto-1-refit` identifica el archivo reajustado utilizado en la demostración del día 30. No son exactamente los pesos del piloto que produjo la comparación. El ensayo corregido con viaje y parada está en `eta-correccion.json`; no sustituyó al modelo en servicio. Las medias horarias agrupan por campo antes de agregar y están en `mae-horario-global.csv`.

## Plan de invierno y pruebas

`decisiones-reales-verificadas.csv` conserva tres momentos reales: uno con empeoramiento superior a 90 segundos pero sin nieve y otros dos sin cumplimiento de ambas condiciones. Ninguno activó el plan.

Los JSON `pruebas-regresion-funciones.json` y `pruebas-mapa-eta.json` son registros de las baterías históricas, de 23 y cinco casos respectivamente. La batería ejecutable del repositorio está en `tests/funciones.test.cjs` y vuelve a probar las funciones exportadas con fechas actuales. No deben confundirse estos ensayos con observaciones de vehículos.

Las capturas seleccionadas están en `docs/screenshots`. Los archivos `vp-*.wc` recogen las medidas de caudal y `consulta-filas.csv` la consulta de medias por minuto. Las salidas de configuración y anotaciones de alertas se conservan en `results`.

## Artefactos fuera de Git

El histórico de errores individuales (aproximadamente 3 MB) y el modelo binario (aproximadamente 1,1 MB) permanecen en el laboratorio. `artifact-manifest.json` registra sus nombres, tamaños y huellas SHA-256. También se excluyen las capturas crudas repetidas de MQTT, los logs, las credenciales y los volúmenes. Las métricas agregadas permiten consultar los resultados sin descargar esas trazas.
