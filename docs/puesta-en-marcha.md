# Puesta en marcha

## Servicios y configuración

Se necesita Docker Compose. Para ETA, Python 3.11 o posterior; las versiones del entorno utilizado están fijadas en `requirements.txt`. En macOS, LightGBM puede requerir OpenMP. Las pruebas JavaScript usan Node.js 20 o posterior.

1. Copiar `.env.example` a `.env` y establecer un token largo de InfluxDB y contraseñas distintas para InfluxDB y Grafana. Por ejemplo, `openssl rand -hex 32` genera un valor aleatorio. No compartir `.env`.
2. Comprobar que los puertos 1883, 9001, 1880, 8086 y 3000 estén libres. Si el laboratorio anterior está arrancado, no ejecutar otro stack en esos puertos.
3. Ejecutar `docker compose config --quiet` y después `docker compose up -d --build`.
4. Abrir Node-RED en `http://localhost:1880` e importar `flows/hsl.json` desde el menú Importar.
5. Editar la configuración compartida **InfluxDB flota**: URL `http://influxdb:8086`, versión 2.0 y token definido en `.env`. El flujo utiliza organización `lab` y bucket `flota`; estos nombres se mantienen fijos en esta configuración. El token del nodo se introduce en el editor y no forma parte de la exportación pública.
6. Desplegar el flujo. El nodo de carga de paradas lee `/data/stops-hsl.json`, montado por Compose. Comprobar que haya cargado 8 389 paradas.
7. Abrir `http://localhost:1880/worldmap` y Grafana en `http://localhost:3000`. Grafana utiliza el usuario `lab` y la contraseña elegida; el datasource `influx-flota` y los paneles se aprovisionan desde `infra/grafana`.

Las imágenes de Mosquitto e InfluxDB siguen sus ramas mayores; Grafana conserva `latest`. Para un despliegue reproducible a largo plazo conviene fijar los digests de las imágenes verificadas. Este repositorio no levanta automáticamente el laboratorio existente ni importa su histórico.

La regla de alerta está exportada en `results/alerta-grafana.json` como registro de configuración. No se aprovisiona automáticamente: hay que recrearla con la condición `retraso_s < -300`, evaluación cada 10 segundos y espera pendiente de 10 segundos. El dashboard, por sí solo, no crea esa regla.

## Entrenamiento y servicio ETA

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
set -a
source .env
set +a
python src/eta_ml.py entrenar
python src/eta_ml.py servir
```

Ajustar `ETA_DESDE` al inicio de los datos que se quieran consultar. Los artefactos se guardan en `artifacts/`, fuera de Git, o en `ETA_ARTIFACT_DIR` si se define. El entrenamiento puede finalizar sin guardar modelo cuando no supera las comprobaciones de datos de su implementación; en ese caso se debe leer el resultado, no arrancar `servir` como si ya existieran pesos nuevos.

El archivo entrenado con los datos originales no está incluido. Sin él, no se reproducen exactamente los pesos de `piloto-1` ni de `piloto-1-refit`. Los resultados de esas sesiones están disponibles como registros históricos, separados de cualquier nuevo ensayo. Para una nueva campaña debe asignarse una versión distinta en el código antes de entrenar y ajustar los filtros de Grafana conscientemente.

No ejecutar dos instancias de `servir`. El servicio usa el identificador MQTT `eta-ml`; una segunda instancia puede desconectar a la primera. Los paneles históricos filtran `piloto-1` y una ventana del 29 de septiembre: en una instalación vacía aparecerán sin datos hasta que se seleccione una campaña disponible.

## Pruebas y cierre

```bash
node --test tests/funciones.test.cjs
python scripts/verificar_publicacion.py
```

Las pruebas son locales y no conectan a brokers ni bases de datos. Para cerrar la adquisición, desactivar las entradas HSL en Node-RED y desconectar HSL en MQTTX. Detener el servicio Python por separado. Si se van a limpiar retenidos, guardar primero los que hagan falta y publicar mensajes vacíos retenidos en los topics concretos. Finalmente, `docker compose stop` conserva los volúmenes.
