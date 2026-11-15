# Laboratorio 2 — NovaMercado

Modelado, API y persistencia integrados en main. Fase 3 (MLflow, Docker Compose y
bootstrap) implementada en fase-3-mlflow-docker, pendiente de revisión por PR.
Airflow y el DAG corresponden a Fase 4 y todavía no están conectados.

## Arranque desde cero

Requisitos: Docker con Compose y los cinco CSV docentes colocados en `data/`:
`historico_ventas.csv`, `tiendas.csv`, `familias.csv`, `feriados.csv`, `costos.csv`.
Conservar nombres y columnas. Los ejemplos JSON son útiles para las pruebas;
los originales y el PDF no se publican ni se incorporan a imágenes.

```bash
cd ~/lab02_pd
cp .env.example .env
```

Editar POSTGRES_PASSWORD en `.env`, usando un valor hexadecimal propio. Puede
generarse con `.venv/bin/python -c 'import secrets; print(secrets.token_hex(24))'`.
Mantener ese valor local; `.env` está ignorado por Git. Ajustar puertos si están
ocupados. Opcionalmente poner en SOURCE_REVISION el resultado de `git rev-parse HEAD`.

```bash
docker compose build
docker compose up
```

La construcción se separa para medir el límite de arranque sin contar el build.
También se puede usar `docker compose up --build`. No se necesitan comandos de
carga de datos, entrenamiento o registro manual. Para segundo plano: `up -d`.

- API: http://localhost:8000; contrato y documentación en `/docs` y `/openapi.json`.
- MLflow: http://localhost:5000; experimento `novamercado-ventas`, modelo
  `novamercado`, alias `champion`. Puertos publicados solo en localhost.
- PostgreSQL del producto no expone puerto al host. Airflow tendrá otra instancia,
  credenciales y volumen propios; no debe reutilizar este DSN ni postgres_data.

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

**Estado parcial de Fase 3:** `/health` responde 200 con `estado=degradado` y
motivo Airflow mientras ese componente no exista. Si MLflow falla, lo añade al
motivo; sin modelo responde 503. No se presenta un estado ok ficticio. El estado
integral ok y su recuperación se verificarán al conectar Airflow en Fase 4.
`POST /admin/reentrenar` sigue devolviendo 503 y los IDs desconocidos 404.

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
No se necesitan otro servidor de DB, almacén de objetos ni colas en esta fase.

```bash
docker compose ps -a
docker compose logs bootstrap
docker compose down
docker compose up
```

`down` conserva los volúmenes. No usar `down -v` para reinicios ni eliminar esos
volúmenes: contienen la operación y los modelos. Datos docentes solo se montan
read-only en bootstrap; API lee el snapshot de PostgreSQL. `.dockerignore` permite
únicamente Dockerfile, requirements y código Python: ni datos ni secretos entran
al contexto. La API corre con un usuario sin privilegios.

Imágenes fijadas: Python 3.14.4 slim-bookworm para API/bootstrap, PostgreSQL 16.11,
MLflow 3.17.2. Health checks ordenan el arranque; en Fase 3 la salud del contenedor
API exige modelo cargado/HTTP 200, aunque el contrato siga indicando Airflow pendiente.

## Entorno local y pruebas

Usar exclusivamente el entorno existente `.venv/` (prompt lab02), Python 3.14.4:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
python -m pytest -q -W error
python -m novamercado.evaluate --output outputs/evaluacion.json
```

Las pruebas de contrato no requieren MLflow activo. Seis pruebas SQL se omiten
si no existe TEST_DATABASE_URL; diez ejemplos docentes se omiten si no está la
carpeta data/ejemplos. Para SQL, definir ese DSN a una DB descartable con permiso
CREATE SCHEMA; se crean esquemas únicos conservados para inspección, sin borrar
datos ajenos. Dos advertencias internas conocidas de MLflow se filtran únicamente
en la prueba de serialización local; las demás advertencias son errores.

Prueba completa de Compose: requiere un proyecto nuevo, puertos libres y la
imagen construida. Crear `.env.prueba` con COMPOSE_PROJECT_NAME diferente,
API_PORT y MLFLOW_PORT propios; también está ignorado por Git.

```bash
docker compose --env-file .env.prueba build
PYTHONPATH=. .venv/bin/python scripts/verify_stack.py --env-file .env.prueba --api-url http://127.0.0.1:18000 --mlflow-url http://127.0.0.1:15000
```

El script verifica arranque vacío, promoción, recarga, alias inválido, caída de
MLflow, reinicio offline y down/up sin borrar volúmenes. Debe apuntar únicamente
al proyecto de prueba: detiene/reinicia sus servicios. Guarda resultados agregados
y logs en outputs/ (ignorado). Si se interrumpe después de promover, puede
continuar con `--resume-after-promotion` usando el mismo archivo de resultados.
Los puertos de las URLs deben coincidir con `.env.prueba`.

Resultados por fase: [Fase 1](RESULTADOS_FASE1.md), [Fase 2](RESULTADOS_FASE2.md),
[Fase 3](RESULTADOS_FASE3.md). Código principal en novamercado/, pruebas en tests/;
reglas en [AGENTS.md](AGENTS.md), fases en [PLAN.md](PLAN.md), decisiones en
[DECISIONES.md](DECISIONES.md).

## Git

main estable. Cada fase autorizada usa rama propia desde main actualizado,
commits, pruebas, push y PR. No hacer merge sin aprobación ni borrar ramas.
No iniciar Fase 4 sin autorización. Tag entrega-lab2 solo desde main final.
