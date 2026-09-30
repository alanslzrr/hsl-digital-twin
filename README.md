# Flota HSL: seguimiento y predicción de llegada

[![Verificar proyecto](https://github.com/alanslzrr/hsl-digital-twin/actions/workflows/verificar.yml/badge.svg)](https://github.com/alanslzrr/hsl-digital-twin/actions/workflows/verificar.yml)

Sistema de seguimiento de tranvías de Helsinki con MQTT, Node-RED, InfluxDB y Grafana. Recibe posiciones de la línea 4, valida los mensajes y muestra los vehículos en un mapa. Añade una decisión meteorológica para el plan de invierno y un servicio experimental de estimación del tiempo de llegada (ETA).

La memoria explica las decisiones y los resultados. Este repositorio conserva la implementación, las configuraciones, las pruebas y los resultados resumidos que permiten estudiar cómo funciona el sistema.

## Recorrido de los datos

HSL publica posiciones y eventos. Node-RED valida y normaliza los mensajes; el broker local distribuye el estado, Worldmap lo representa e InfluxDB lo conserva. Grafana consulta el histórico. Open-Meteo aporta contexto para la decisión meteorológica y el servicio Python compara un modelo LightGBM con una estimación basada en distancia y velocidad.

![Arquitectura del sistema](docs/diagrams/arquitectura.svg)

## Dónde empezar

- [PDF de la memoria](docs/memoria.pdf): versión maquetada con portada UIE y figuras.
- [Memoria técnica](docs/memoria.md): explicación del sistema con figuras y resultados.
- [Puesta en marcha](docs/puesta-en-marcha.md): servicios, configuración privada e importación de flujos.
- [Contrato y filtros](docs/contrato-mqtt.md): topics completos, unidades y condiciones.
- [Evaluación y resultados](docs/resultados.md): ventanas, versiones y errores del ETA.
- [Seguridad y datos](SECURITY.md): qué se publica y qué se conserva fuera de Git.

## Estructura

| Carpeta | Contenido |
| --- | --- |
| `src/` | Preparación, entrenamiento y servicio ETA |
| `flows/` | Flujo completo de Node-RED |
| `infra/` | Docker, Mosquitto y aprovisionamiento de Grafana |
| `data/` | Coordenadas de paradas necesarias para calcular distancias |
| `results/` | Métricas agregadas y registros pequeños de comprobación |
| `tests/` | Pruebas aisladas; no publican mensajes ni escriben en InfluxDB |
| `docs/` | Explicaciones, capturas y diagramas |

## Lectura de los resultados

La comparación cerrada del 29 de septiembre de 2026 contiene 20 786 predicciones: MAE global de 29,39 s para la base y 15,89 s para el modelo. En el grupo mayor, vehículos en marcha a menos de 30 segundos de llegar, gana la base: 3,98 s frente a 11,62 s. El modelo no se presenta como superior en todas las situaciones.

## Alcance

El proyecto es un entorno de laboratorio. No actúa sobre vehículos ni activa recursos físicos. El histórico individual y el archivo de pesos no se distribuyen en Git. Clonar el repositorio permite consultar la implementación y las métricas; para generar nuevas predicciones hay que configurar el entorno, recopilar datos y disponer de un modelo entrenado.

El historial de Git comienza con la publicación y organización de este repositorio. Las fechas de los ensayos anteriores se conservan en los resultados; los commits no pretenden representar retrospectivamente aquellas sesiones.

## Regenerar el PDF

`bash docs/pdf/build.sh` compila la memoria desde Markdown mediante Pandoc y LaTeX. Requiere `pandoc`, `pdflatex`, `latexmk`, `rsvg-convert` y Python 3. Las capturas y los diagramas se toman de `docs/`; los temporales se excluyen de Git.
