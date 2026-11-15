# Laboratorio 2 — NovaMercado

Modelado y validación temporal implementados en `fase-1-modelado`, pendientes de
revisión por PR. Repositorio: https://github.com/JoseEspanaD/lab02-product-development.
API e infraestructura todavía no implementadas; no hay comando Docker operativo.

## Preparar el entorno existente

```bash
cd ~/lab02_pd
source .venv/bin/activate
python --version
python -m pip install -r requirements.txt
python -m pip check
```

Usar exclusivamente `.venv/` (prompt `lab02`), con Python 3.14.4. Las versiones
fijadas fueron instaladas con wheels compatibles y probadas en ese entorno.
La documentación oficial de [scikit-learn](https://scikit-learn.org/stable/install)
describe sus requisitos; la versión de Python de futuros contenedores se validará
al integrar Airflow. No instalar paquetes globalmente.

Colocar en `data/` los archivos docentes `historico_ventas.csv`, `tiendas.csv`,
`familias.csv`, `feriados.csv` y `costos.csv`, conservando sus nombres y columnas.
El PDF, los datos y sus ejemplos se mantienen solo localmente; no se modifican
ni publican. No colocar secretos en archivos versionados.

## Evaluar y probar

```bash
.venv/bin/python -m pytest -q -W error
.venv/bin/python -m novamercado.evaluate --data-dir data --output outputs/evaluacion.json
```

El evaluador lee los originales, entrena baseline y ML, calibra cantidades por
costo y produce métricas globales, por familia y por mes, hashes de datos,
versiones, cortes y tiempos. `outputs/` está ignorado por Git. El comando devuelve
error si el ML no mejora el costo del baseline; no promueve modelos automáticamente.

Por defecto: entrenamiento 2024-03-01–2025-10-31; calibración 2025-11-01–2025-12-31;
evaluación 2026-01-01–2026-02-28. Se pueden cambiar los cortes con
`--calibration-start`, `--test-start` y `--test-end` para otros históricos;
los cortes deben ser ordenados y contener filas. Test posterior a calibración,
sin split aleatorio ni ajuste de parámetros a partir del test.

La evaluación reproduce pronósticos diarios de un paso: ventas hasta el día
anterior disponibles y promociones del día conocidas por solicitud. No representa
un pronóstico de varios meses sin recibir observaciones intermedias.

## Código reutilizable

- `novamercado/data.py`: carga, integridad y huellas SHA-256.
- `features.py`: `build_features(history, requests, stores, holidays)`, conserva
  el orden de solicitudes y usa exclusivamente ventas anteriores a cada fecha.
- `models.py`: baseline estacional y regresor global, métodos `fit`/`predict`.
- `costs.py`: calibrador con `fit`/`suggest`, métrica de costo, MAE y RMSE.
- `evaluate.py`: protocolo temporal y CLI; pruebas sintéticas en `tests/`.

Para inferencia, generar X con `build_features`, obtener venta esperada con
`model.predict(X)` y cantidad con `calibrator.suggest(familias, predicciones)`.
Usar el modelo/encoder y calibrador ajustados antes de la fecha pronosticada.
El objeto modelo no contiene el histórico: las observaciones se proporcionan a
la función de features. La API validará identidades y solicitudes en la Fase 2.

Resultados: [RESULTADOS_FASE1.md](RESULTADOS_FASE1.md). Reglas y contexto:
[AGENTS.md](AGENTS.md); requisitos y fases: [PLAN.md](PLAN.md); decisiones y
limitaciones: [DECISIONES.md](DECISIONES.md).

## Git y revisión

main es estable. Cada fase autorizada parte de main actualizado en una rama
propia, con commits, pruebas, push y PR hacia main. Nunca hacer merge sin
aprobación ni eliminar las ramas después. No iniciar Fase 2 sin autorización.
El tag `entrega-lab2` se creará desde main al finalizar el laboratorio.
