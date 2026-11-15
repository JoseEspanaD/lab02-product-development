# Laboratorio 2 — NovaMercado

Fases 1–4 integradas en main. Fase 5 verifica el producto completo y prepara
la entrega en fase-5-verificacion-entrega; tag pendiente de aprobación.

## Arranque desde cero

Requisitos: Git y Docker con Compose >=2.17 (incluye additional_contexts).
Reservar al menos 5,6 GiB de RAM para Docker y ejecutar un solo stack del laboratorio.
No se necesita Python ni un entorno virtual en el host para levantar el producto.
Clonar el repositorio y colocar los cinco CSV docentes en `data/`:
`historico_ventas.csv`, `tiendas.csv`, `familias.csv`, `feriados.csv`, `costos.csv`.
Conservar nombres y columnas. Los ejemplos JSON son útiles para las pruebas;
los originales y el PDF no se publican ni se incorporan a imágenes.

```bash
git clone https://github.com/JoseEspanaD/lab02-product-development.git
cd lab02-product-development
mkdir -p data
# Colocar aquí los cinco CSV indicados arriba.
cp .env.example .env
```

Editar POSTGRES_PASSWORD, AIRFLOW_PASSWORD, AIRFLOW_DB_PASSWORD y
AIRFLOW_SECRET_KEY en `.env`, usando valores hexadecimales distintos. Por cada
valor ejecutar el siguiente comando (también descarga la imagen base si falta):

```bash
docker run --rm python:3.14.4-slim-bookworm python -c 'import secrets; print(secrets.token_hex(24))'
```

Generar AIRFLOW_FERNET_KEY con:

```bash
docker run --rm python:3.14.4-slim-bookworm python -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
```

Guardar las claves solo en `.env`. `.env` está ignorado por Git. Ajustar puertos si están
ocupados. Opcionalmente poner en SOURCE_REVISION el resultado de `git rev-parse HEAD`.

```bash
COMPOSE_PARALLEL_LIMIT=1 docker compose build
docker compose up
```

La construcción se separa para medir el límite de arranque sin contar el build.
También se puede usar `docker compose up --build`. No se necesitan comandos de
carga de datos, entrenamiento o registro manual. Para segundo plano: `up -d`.

- API: http://localhost:8000; contrato y documentación en `/docs` y `/openapi.json`.
- MLflow: http://localhost:5000; experimento `novamercado-ventas`, modelo
  `novamercado`, alias `champion`. Puertos publicados solo en localhost.
- PostgreSQL del producto no expone puerto al host. Airflow tiene su propia instancia
  airflow-db y volumen; no reutiliza este DSN ni postgres_data.

El primer arranque crea el esquema, carga un snapshot transaccional de los cinco
CSV, entrena baseline/ML y registra un artefacto con modelo, encoder y calibración.
Solo asigna champion si el ML reduce estrictamente el costo del baseline en
validación temporal. Una tarea bootstrap finita coordina ese trabajo bajo un
bloqueo PostgreSQL. La API arranca después y descarga el modelo registrado.

En reinicios posteriores, bootstrap reutiliza snapshot y alias: no relee los
CSV, no vuelve a importar, entrenar ni crear una versión. Si quedó una versión
registrada elegible pero el alias no llegó a asignarse, la valida y recupera el
alias sin entrenar. Versiones no elegibles no se activan automáticamente.
El snapshot publicado es inmutable; no se reemplaza silenciosamente al cambiar
archivos. Los datos nuevos de operación se guardan en observaciones.

## Contrato y uso

```bash
curl -s http://localhost:8000/modelo
curl -s http://localhost:8000/health
curl -s -H 'Content-Type: application/json' --data-binary @data/ejemplos/prediccion_valida.json http://localhost:8000/v1/prediccion
curl -s -H 'Content-Type: application/json' --data-binary @data/ejemplos/observacion_valida.json http://localhost:8000/v1/observaciones
```

Predicción devuelve versión registrada en texto, venta esperada, cantidad entera
no negativa y calidad. Observaciones son idempotentes: el reenvío idéntico guarda
cero filas. PostgreSQL audita cuerpo original, canónico, correcciones, resultado,
promociones y versión; las predicciones repetidas se conservan por separado.
Las políticas generales y E01–E10 están en DECISIONES.md.

`/health` responde ok cuando modelo, PostgreSQL, MLflow y Airflow (metadatos,
scheduler y DAG disponible) funcionan. Ante una dependencia caída responde 200
degradado con motivo; sin modelo responde 503. La inferencia no consulta Airflow.

## Airflow y administración

Airflow: http://localhost:8080; usuario y contraseña de `.env`. Base PostgreSQL
propia en airflow-db, con credenciales y volumen distintos a los del producto.
LocalExecutor, scheduler y webserver en un contenedor supervisado; sin Redis/Celery.
Airflow 2.11.1 usa Python 3.12 y ejecuta el entrenamiento con el mismo runtime
Python 3.14.4 y dependencias fijadas de la API, copiado durante el build. No se
instala Airflow en el entorno local ni se cambia su versión de Python.

```bash
curl -s -X POST http://localhost:8000/admin/reentrenar
curl -s http://localhost:8000/admin/reentrenar/ID_DEVUELTO
```

El POST sin cuerpo devuelve 202 e id real de Airflow; si hay una ejecución activa,
reutiliza su id bajo bloqueo PostgreSQL. Si Airflow/DAG no están disponibles, 503.
GET devuelve en_curso, exitoso o fallido; al terminar incluye promovido, version
vigente al terminar y motivo. ID desconocido: 404; Airflow no accesible: 503.
Las ejecuciones exitosas sin mejora también son exitoso, con promovido=false.

DAG novamercado_reentrenar: schedule=None (disparo exigido por API), catchup=False,
una ejecución y una tarea activas. entrenar_evaluar_promover → finalizar (all_done).
Un reintento tras 10 s; tarea principal limitada a 4 minutos y DAG a 9 minutos.
El finalizador persiste el resultado y mantiene fallido el DAG si el ajuste falla.
El PDF no exige un cron ni una política específica de reintentos.

El corte simulado es la última fecha con ventas y promociones disponibles, nunca
la fecha real ni logical_date. Se une histórico con observaciones; la observación
corrige ventas y la última predicción aporta promociones. Sin ella se conserva la
promoción publicada si la clave existe en histórico; si tampoco existe, se excluye
esa etiqueta del ajuste y se registra la cobertura. La inferencia sí conserva
esas ventas como historia de lags. Hash del snapshot y cobertura van a MLflow.
Se mantienen entrenamiento/calibración/validación separados de 60 días; sin ventana
posterior a selección del vigente no se ajusta ni promueve y se explica el motivo.

Las tareas comparten el bloqueo del bootstrap/promoción. Un reintento recupera
una versión ya registrada para ese run_id, sin duplicar el ajuste/registro; no
sobrescribe un champion posterior. Resultado terminal inmutable en ejecuciones
(PostgreSQL del producto); estado y ejecución reales en la DB propia de Airflow.
Una caída de MLflow, Airflow o un trabajo fallido conserva el modelo cargado.

## Modelo, cortes y promoción

El bootstrap usa por defecto validación de 60 días hasta 2025-11-16, calibración
de 60 días inmediatamente anterior y entrenamiento anterior a ambas. Esto
permite atender el ejemplo del 2025-11-17 sin aprender ni seleccionar con datos
futuros. El corte es simulado y configurable; nunca se compara con el reloj.
Un modelo no atiende fechas anteriores a su selección: devuelve 503 explicativo
en lugar de usar información futura. Al promover un modelo más reciente cambia
su cobertura temporal; consultar la versión vigente antes de repetir ejemplos
históricos. La evaluación oficial es posterior al histórico.

`training.py` comparte ajuste y validación para bootstrap y futuros trabajos.
Se registran MAE, RMSE, costo faltante/sobrante, cortes, parámetros, tiempo,
hashes SHA-256, metadatos de los cinco datasets y snapshot de código. Se registra
modelo/encoder/calibrador como un artefacto MLflow con flavor sklearn.
Se usa cloudpickle para los objetos propios del producto y solo se cargan desde
su Registry configurado. No se suben filas originales como ejemplos de modelo.

`train_and_register` compara candidato, baseline y vigente sobre las mismas
filas futuras al ajuste/calibración. Requiere una ventana posterior a la selección
del vigente, métricas finitas y costo estrictamente menor que ambos. Los empates
y candidatos peores quedan sin promoción. El artefacto se descarga y valida
antes de mover el alias; todos los escritores del producto usan el mismo lock.
No hay operación SQL posterior al cambio de alias: cerrar la sesión libera el lock.

La API consulta champion cada 10 s en segundo plano, valida el artefacto y guarda
una caché atómica en volumen antes de intercambiar el modelo en memoria. Inferencia
no consulta MLflow y puede continuar durante su caída, incluso tras reiniciar la
API si existe caché válida. El refresco conserva el modelo anterior ante errores,
artefactos incompatibles, caché no escribible o alias no elegible. Health invalida
el estado del Registry si pasan 45 s sin verificación reciente. Timeouts de red
acotados y sin reintentos automáticos largos.

## Persistencia y operación

Volúmenes de Compose: postgres_data (operación/snapshot), mlflow_data (SQLite de
metadatos/Registry y artefactos) y model_cache (último modelo utilizable). SQLite
solo es backend interno de MLflow; la persistencia del producto es PostgreSQL.
Airflow añade airflow_db_data y airflow_logs; no usa la base del producto.

```bash
docker compose ps -a
docker compose logs bootstrap
docker compose down
docker compose up
```

`down` conserva los volúmenes. No usar `down -v` para reinicios ni eliminar esos
volúmenes: contienen la operación y los modelos. Datos docentes solo se montan
read-only en bootstrap; API lee el snapshot de PostgreSQL. `.dockerignore` permite
únicamente Dockerfiles, requirements, DAGs y código Python: ni datos ni secretos entran
al contexto. La API corre con un usuario sin privilegios.

Imágenes fijadas: Python 3.14.4 slim-bookworm para API/bootstrap, PostgreSQL 16.11,
MLflow 3.17.2 y Airflow 2.11.1-python3.12. Health checks ordenan el arranque; la salud del contenedor API exige HTTP 200
y el endpoint informa ok solo cuando también están disponibles sus dependencias.

## Entorno local y pruebas

Usar exclusivamente el entorno existente `.venv/` (prompt lab02), Python 3.14.4:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m pytest -q -W error
python -m novamercado.evaluate --output outputs/evaluacion.json
```

Las pruebas de contrato no requieren MLflow activo. Once pruebas SQL se omiten
si no existe TEST_DATABASE_URL; diez ejemplos docentes se omiten si no está la
carpeta data/ejemplos. Para SQL, definir ese DSN a una DB descartable con permiso
CREATE SCHEMA; se crean esquemas únicos conservados para inspección, sin borrar
datos ajenos. Dos advertencias internas conocidas de MLflow se filtran únicamente
en la prueba de serialización local; las demás advertencias son errores.

Prueba actual de Compose/Airflow: preparar `.env.prueba` con todas las variables
de `.env.example`, proyecto nuevo y puertos propios, incluidos AIRFLOW_PORT.
Ejecutar solo un stack del laboratorio a la vez en equipos con poca RAM.

```bash
COMPOSE_PARALLEL_LIMIT=1 docker compose --env-file .env.prueba build
.venv/bin/python scripts/verify_airflow.py --env-file .env.prueba --api-url http://127.0.0.1:18004
.venv/bin/python scripts/verify_airflow_details.py --env-file .env.prueba
```

El primer script cubre DAG real, promoción, id activo reutilizado, falta de datos,
fallo de entrenamiento con reintento, caídas de servicios y persistencia. El segundo
comprueba estados/tareas reales, seis datasets de linaje y caída de la DB Airflow.
Conservar el mismo proyecto entre ambos. Los scripts detienen/reinician sus
servicios y conservan volúmenes; evidencia agregada en outputs/, ignorado.

Para medir arranque vacío, usar otro proyecto nuevo sin contenedores ni volúmenes
previos y detener antes el de prueba anterior:

```bash
.venv/bin/python scripts/verify_cold_start.py --env-file .env.arranque --api-url http://127.0.0.1:18005
```

El script de Fase 3 `scripts/verify_stack.py` se conserva para ensayos específicos
del Registry/caché; también requiere proyecto nuevo y variables Airflow completas.

Resultados por fase: [Fase 1](RESULTADOS_FASE1.md), [Fase 2](RESULTADOS_FASE2.md),
[Fase 3](RESULTADOS_FASE3.md), [Fase 4](RESULTADOS_FASE4.md),
[Fase 5](RESULTADOS_FASE5.md). Código principal en novamercado/, pruebas en tests/;
reglas en [AGENTS.md](AGENTS.md), fases en [PLAN.md](PLAN.md), decisiones en
[DECISIONES.md](DECISIONES.md).

## Git

main estable. Cada fase autorizada usa rama propia desde main actualizado,
commits, pruebas, push y PR. No hacer merge sin aprobación ni borrar ramas.
Fase 5 autorizada; no hacer merge ni crear entrega-lab2 sin aprobación.
El tag se creará desde main final después de integrar el PR.

Memoria: Compose limita Airflow a 1792 MiB, API 512 MiB, MLflow 1024 MiB y cada
PostgreSQL a 256 MiB. Bootstrap (768 MiB) termina antes de iniciar Airflow.
Una sola tarea/parser/worker y hilos numéricos a uno reducen picos. En WSL con
poca RAM evitar mantener copias anteriores del stack ejecutándose simultáneamente.
Tras reiniciar Windows, iniciar Docker Desktop y habilitar integración WSL para
Ubuntu antes de usar Compose. No borrar volúmenes para recuperar el servicio.

## Auditoría final reproducible

La lectura local del PDF usa `python -m pip install -r requirements-auditoria.txt`
dentro de `.venv`; ese lector no forma parte de las imágenes ni de la inferencia.
Para los ensayos integrales usar un proyecto nuevo `lab02fase5*`, con puertos libres,
`.env.prueba` y los datos originales disponibles en `data/`. Crear `outputs/` antes.
Tras construir, ejecutar en orden:

```bash
mkdir -p outputs
.venv/bin/python scripts/verify_cold_start.py --env-file .env.prueba --api-url http://127.0.0.1:18006 --output outputs/fase5_arranque.json
.venv/bin/python scripts/verify_airflow.py --env-file .env.prueba --api-url http://127.0.0.1:18006 --output outputs/fase5_integracion.json
.venv/bin/python scripts/verify_airflow_details.py --env-file .env.prueba --output outputs/fase5_detalles.json
.venv/bin/python scripts/verify_delivery.py --env-file .env.prueba --output outputs/fase5_operacion.json
```

Configurar API_PORT=18006, MLFLOW_PORT=15006, AIRFLOW_PORT=18086 para esos comandos.
Estos ensayos detienen servicios del proyecto indicado y conservan sus volúmenes.
El arranque vacío rechaza proyectos que ya tengan contenedores o volúmenes. No
usar el proyecto principal. Las ventas sintéticas verifican funcionamiento; la
mejora predictiva se evalúa separadamente con el histórico real retenido.
