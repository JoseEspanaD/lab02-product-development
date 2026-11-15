# Laboratorio 2 — NovaMercado

Fase 1 integrada. API, limpieza y persistencia implementadas en
`fase-2-api-persistencia`, pendientes de revisión por PR. Repositorio: https://github.com/JoseEspanaD/lab02-product-development.
La infraestructura completa y Docker Compose siguen pendientes de la Fase 3.

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
aprobación ni eliminar las ramas después. No iniciar Fase 3 sin autorización.
El tag `entrega-lab2` se creará desde main al finalizar el laboratorio.


## API local — Fase 2

Se necesitan los cinco CSV docentes en data/ y un PostgreSQL propio del producto.
No utilizar la base de Airflow ni una DB con datos ajenos para pruebas.

Si no hay PostgreSQL disponible, se puede iniciar únicamente la DB del producto
(sin desplegar MLflow, Airflow ni Compose). Crear `.env.postgres` local con las
variables POSTGRES_USER, POSTGRES_PASSWORD y POSTGRES_DB, y una contraseña
propia. Ese archivo está ignorado por Git. Usar usuario/base lab02 para coincidir
con la plantilla; no usar la palabra REEMPLAZAR como contraseña.

```bash
docker run -d --name lab02-postgres --env-file .env.postgres -p 127.0.0.1:55433:5432 -v lab02-postgres:/var/lib/postgresql/data postgres:16.11
cp .env.example .env
```

Editar DATABASE_URL en `.env` con las credenciales reales y esperar que la DB
esté lista. Cargar las variables en la terminal e inicializar el esquema:

```bash
set -a
source .env
set +a
.venv/bin/python -m novamercado.repository
.venv/bin/python -m uvicorn novamercado.api:local_app --factory --host 127.0.0.1 --port 8000
```

La inicialización del esquema no borra filas al repetirse. El volumen de PostgreSQL
conserva los datos después de reiniciar; no eliminarlo. No hay bootstrap completo
ni artefacto persistido de modelo en esta fase. La factoría local entrena el ML de
Fase 1 y calibra los últimos 60 días anteriores al fin del histórico; al reiniciar
API vuelve a entrenar en memoria. Esto se reemplazará por MLflow en Fase 3.

Para solicitudes dentro del histórico se construye un bundle anterior a esa fecha:
ninguna venta actual/futura participa en el ajuste, calibración o features. Solo
se conserva un bundle en memoria; la versión `local-FECHA-HASH` y alias `local`
identifican realmente el cargado. No son una versión/alias registrados en MLflow.
La historia de features combina CSV con observaciones de DB anteriores al día;
las correcciones operativas prevalecen sobre una fila histórica. Las promociones
se toman de la solicitud actual y se guardan para el reentrenamiento futuro.

```bash
curl -s http://127.0.0.1:8000/modelo
curl -s http://127.0.0.1:8000/health
curl -s -H 'Content-Type: application/json' --data-binary @data/ejemplos/prediccion_valida.json http://127.0.0.1:8000/v1/prediccion
curl -s -H 'Content-Type: application/json' --data-binary @data/ejemplos/observacion_valida.json http://127.0.0.1:8000/v1/observaciones
```

| Endpoint | Estado actual |
|---|---|
| POST /v1/prediccion | 200 con versión, predicciones y calidad; 422 si se rechaza; 503 ante modelo/DB no disponibles |
| POST /v1/observaciones | 200 con nuevos/modificados y calidad; reenvío idéntico cuenta 0; 422 para inválidos |
| GET /modelo | Nombre, alias y versión del modelo cargado; 503 si no hay modelo |
| GET /health | 200 degradado mientras falten MLflow/Airflow; 503 sin modelo; 200 ok solo con todas las dependencias conectadas |
| POST /admin/reentrenar | 503 hasta conectar Airflow; adaptador preparado para 202 con id real |
| GET /admin/reentrenar/{id} | 404 para desconocido; contrato de estados preparado para el adaptador futuro |

Documentación interactiva en /docs y esquema en /openapi.json. Los ejemplos de
administración exitosa de las pruebas usan dobles explícitos: no hay ejecuciones
reales de DAG ni respuestas exitosas simuladas en la aplicación local.

## Pruebas de API y PostgreSQL

```bash
.venv/bin/python -m pytest -q -W error
```

Sin TEST_DATABASE_URL, cinco pruebas de PostgreSQL se omiten explícitamente.
Los diez ejemplos oficiales se omiten si no está la carpeta docente. El resto
usa datos sintéticos y adaptadores de prueba, sin servicios MLflow/Airflow.

Para integración, definir TEST_DATABASE_URL con el DSN de una base descartable
de pruebas y ejecutar el mismo comando. Requiere permiso CREATE SCHEMA. Cada
prueba crea un esquema único y lo conserva para inspección en esa DB aislada;
no se truncan tablas ni se borran recursos ajenos. No apuntar a producción.
En esta fase se ejecutó la suite completa con PostgreSQL 16.11 en un contenedor
exclusivo de pruebas, volumen lab02-fase2-postgres y puerto local 55432.
Resultados y persistencia tras reinicio: [RESULTADOS_FASE2.md](RESULTADOS_FASE2.md).
