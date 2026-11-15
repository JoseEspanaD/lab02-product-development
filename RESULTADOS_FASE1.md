# Resultados de Fase 1

Evaluación reproducible con `.venv/bin/python -m novamercado.evaluate`.
Python 3.14.4; semilla 42; máximo dos hilos en el ajuste/predicción.
Las métricas son agregadas; no se publican datos originales ni predicciones por fila.

## Protocolo temporal

| Partición | Desde | Hasta | Filas |
|---|---|---|---:|
| entrenamiento | 2024-03-01 | 2025-10-31 | 68652 |
| calibracion | 2025-11-01 | 2025-12-31 | 7320 |
| evaluacion | 2026-01-01 | 2026-02-28 | 7080 |

El modelo se ajusta únicamente con entrenamiento; los cuantiles por costo,
únicamente con calibración. Las observaciones de días anteriores de cada bloque
alimentan las features del siguiente día, sin reentrenar el estimador.
El baseline recibe la misma historia y también se calibra por costo.

## Evaluación final: enero–febrero 2026

| Métrica | Baseline estacional | HistGradientBoosting |
|---|---:|---:|
| filas | 7080.0000 | 7080.0000 |
| mae | 59.7163 | 39.4656 |
| rmse | 111.1184 | 72.5105 |
| costo_total | 307713.4000 | 195030.0000 |
| costo_medio | 43.4623 | 27.5466 |
| entrenamiento_segundos | 0.0140 | 1.4447 |

Reducción de costo: **36.62 %**.
Duración completa medida: 3.41 s (carga, features, ajuste, calibración y evaluación).
Estos tiempos pertenecen a este equipo; el límite del producto completo se comprobará
en fases posteriores. No constituyen tiempos de Docker, MLflow ni Airflow.

## Costo por familia

| Familia | Baseline | ML | Reducción % |
|---|---:|---:|---:|
| abarrotes | 40057.60 | 26008.00 | 35.07 |
| bebe | 3512.90 | 2775.30 | 21.00 |
| bebidas | 33712.80 | 19930.20 | 40.88 |
| carnes | 49805.00 | 29086.50 | 41.60 |
| cuidado_personal | 6288.90 | 3886.60 | 38.20 |
| frutas_verduras | 45269.00 | 30588.00 | 32.43 |
| lacteos | 42414.20 | 29147.40 | 31.28 |
| licores | 7065.90 | 3671.00 | 48.05 |
| limpieza | 7714.60 | 4596.80 | 40.41 |
| mascotas | 2618.40 | 2259.60 | 13.70 |
| panaderia | 49312.50 | 30862.00 | 37.42 |
| snacks | 19941.60 | 12218.60 | 38.73 |

## Costo por mes

| Mes | Baseline | ML |
|---|---:|---:|
| 2026-01 | 200567.60 | 103353.20 |
| 2026-02 | 107145.80 | 91676.80 |

## Verificación

- `python -m pytest -q -W error`: 25 pruebas aprobadas, sin advertencias.
- `python -m pip check`: sin dependencias incompatibles.
- Comparación SHA-256 de todos los archivos originales antes/después: sin cambios.
- `git diff --check`: sin errores de espacios.
- Pruebas con datos sintéticos: independencia de ventas actuales/futuras, equivalencia
  lote/secuencia diaria, lag por calendario ante huecos, apertura, eventos locales y
  nacionales, promociones de solicitud, orden, costo asimétrico, enteros no negativos,
  splits cronológicos, carga inválida y evaluación completa sin servicios externos.

## Huellas de los cinco CSV usados

| Archivo | SHA-256 |
|---|---|
| historico_ventas.csv | `573c3e358242717da6c19d42ab38ff83aa2c2fec9368c55220dd07822554beda` |
| tiendas.csv | `ea80d5dcd98cc9dcddff34234a196787dc4f45317e41596cf7b577301df96a1c` |
| familias.csv | `cd52ebf6613d4eabd8227d3e9305ff833ace0a83b40b81b6668f726121495ce1` |
| feriados.csv | `d655fc58b3c90391b555108e4a4c8887a8053a65c395458be61f3061e450ecbc` |
| costos.csv | `0baee4424f183f0394aaf0e06f5ca633f3b5fe9a77c6985fc1d1a2b628ac00e4` |

## Limitaciones

Es un único bloque de evaluación posterior de dos meses, sin búsqueda de hiperparámetros.
No demuestra rendimiento en el período oculto, todos los feriados o cambios de demanda.
La simulación supone que las observaciones llegan antes del siguiente pronóstico.
No se ha probado todavía con el servicio o el DAG; no hay promoción automática ni
artefacto registrado en MLflow. No se avanzó a la Fase 2.
