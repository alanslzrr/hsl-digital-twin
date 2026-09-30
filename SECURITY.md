# Seguridad y publicación de datos

Los tokens y contraseñas se definen en `.env`, excluido de Git. `.env.example` contiene únicamente nombres de variables y valores no sensibles. No se publican exportaciones de credenciales de Node-RED, modelos pickle, volúmenes Docker, bases de datos, logs de procesos ni capturas crudas completas de MQTT.

Los puertos de Compose se publican solo en `127.0.0.1`. El broker local permite conexiones anónimas dentro del entorno de laboratorio; este diseño no es apropiado para exponerlo a Internet. Node-RED tampoco tiene autenticación configurada por defecto. TLS, usuarios y permisos por topic deben añadirse antes de cualquier exposición fuera del equipo.

La contraseña inicial de InfluxDB solo se aplica al inicializar un volumen vacío. Cambiar `.env` no rota las credenciales que ya existen en un volumen. Nunca ejecutar `docker compose down -v` para resolver una contraseña sin guardar antes los datos necesarios.

`results/artifact-manifest.json` identifica por tamaño y SHA-256 los artefactos que se conservan localmente. No contiene sus bytes. Las coordenadas de paradas y las métricas agregadas sí se incluyen por ser necesarias para explicar el proyecto.

Los archivos pickle ejecutan código al cargarse: utilizar únicamente modelos propios y de procedencia conocida.
