# Resultados Fase 4 — Airflow y reentrenamiento

Implementación en fase-4-airflow-reentrenamiento desde main 7cf2a4d (PR #3
fusionado y verificado). PR de esta fase pendiente de revisión; sin merge ni tag.

## Componentes y contrato

- Airflow 2.11.1-python3.12, LocalExecutor, scheduler/webserver supervisados en
  airflow. PostgreSQL 16.11 independiente en airflow-db, credenciales y volumen
  propios. Sin Redis/Celery y sin instalar Airflow en .venv.
- Runtime de ML Python 3.14.4 idéntico al de API/bootstrap dentro de Airflow.
  requirements.txt se conserva: no se añadieron dependencias locales/globales.
- DAG novamercado_reentrenar bajo demanda (schedule=None), catchup=False, una
  ejecución/tarea activa. entrenar_evaluar_promover → finalizar (all_done).
  Un reintento tras 10 s; tarea principal 4 min, finalización 30 s, DAG 9 min.
  El PDF no fija cron ni cantidad de reintentos; estos son límites del producto.
- POST /admin/reentrenar sin cuerpo: 202/id real; reutiliza ejecución activa
  bajo bloqueo SQL. Airflow/DAG no disponible: 503. GET ID desconocido: 404;
  en_curso y terminal exitoso/fallido con promovido, version y motivo.
- /health verifica modelo, producto, MLflow y Airflow (DB/scheduler/DAG); sin
  modelo 503, dependencia caída 200/degradado, todas disponibles 200/ok.

## Ejecuciones reales y promoción

Proyecto Docker exclusivo lab02fase4, API 18004, MLflow 15004 y Airflow 18084.

| Ejecución | Estado real Airflow | Resultado API | Versión |
|---|---|---|---|
| api__e8d44ad359e048ceb034a9d12444daa7 | success | exitoso, promovido=true | 2 |
| api__8d2bbca6329c4436ba8c46cb15e63f25 | success | exitoso, promovido=false; datos nuevos insuficientes | 2 |
| api__bb80c6d3363947b4bbe84628ee01092a | failed | fallido, promovido=false; MLflow detenido | 2 |

El primer POST repetido durante la ejecución devolvió el mismo ID. El DAG
fallido ejecutó dos intentos de la tarea principal y dos del finalizador; ambas
quedaron failed. No se sustituyó champion durante el fallo.

Se guardaron doce observaciones sintéticas de tienda 1 para 2026-03-01, con
ventas redondeadas de una predicción, exclusivamente para probar la integración.
Su reenvío guardó cero filas. Las promociones proceden de esa solicitud guardada.
No son evidencia de demanda real nueva ni una estimación independiente de mejora.

MLflow registró run 15a39a5f19f147fea4fed7c1c9898d7f y versión 2. Alias
novamercado@champion=2. Validación hasta 2026-03-01: 7092 filas comunes;
ajuste/calibración anteriores. Se conserva la guarda de validación posterior
a la selección del vigente. Métricas de este ensayo, incluidas las doce filas
sintéticas:

| Modelo | MAE | RMSE | Costo total |
|---|---:|---:|---:|
| Baseline | 59,6941 | 111,0543 | 308326,80 |
| Vigente v1 | 39,4076 | 72,3890 | 197243,90 |
| Candidato v2 | 39,6891 | 72,0310 | 195119,30 |

Promoción por costo estrictamente menor que baseline y vigente (1,08 % frente
al vigente); MAE no es condición de promoción. Linaje: cinco datasets publicados
y un sexto snapshot lógico con observaciones, SHA-256, cobertura 12 recibidas/12
usadas/0 sin promociones e ID del DAG. No se publicaron filas en artefactos de
linaje. Las huellas del bundle mantienen compatibilidad con catálogos de la API.

## Tiempos, persistencia y fallos

| Verificación | Resultado medido |
|---|---:|
| Arranque vacío integral, sin build | 100,47 s, health=ok |
| Arranque recuperando el ensayo interrumpido | 142,06 s, health=ok |
| DAG promovido: POST → terminal consultado | 31,56 s |
| Ajuste/calibración/evaluación interno | 5,40 s |
| Consulta que confirmó v2 después del terminal detectado | 0,29 s |
| DAG fallido con reintento | 56,65 s |
| Detección de MLflow detenido | 0,18 s |
| Recuperación de MLflow | 24,43 s |
| Recuperación de Airflow detenido | 48,79 s |
| Recuperación de PostgreSQL de Airflow | 3,57 s |
| Reinicio completo conservando volúmenes | 85,12 s, health=ok |

La versión 2 ya estaba cargada al consultar tras detectar el fin del DAG (sondeo
cada 2 s); 0,29 s es duración de esa comprobación, no una latencia exacta desde
el timestamp de Airflow. Incluso contando todo el DAG y la comprobación, la
cota observada es menor de 32 s y del límite de 120 s. No se reinició la API
para cargar el candidato. Las consultas de /modelo describen el modelo servido.

Inferencia idéntica con MLflow caído, con Airflow detenido y durante la caída
de airflow-db. POST administrativo devolvió 503 cuando Airflow/DB no podían
iniciar trabajos. El producto conserva su propia DB accesible en esos casos.
Tras down/up sin -v se conservaron doce observaciones y tres ejecuciones,
sus resultados consultables, Registry/alias y modelo 2; bootstrap informó
trained=false/imported=false. No se borró ningún volumen.

Arranque vacío independiente en lab02fase4cold (puertos 18005/15005/18085),
sin ejecutar dos stacks del laboratorio simultáneamente. Bootstrap importó
datos y entrenó versión 1 por sí solo; health=ok en 100,47 s. Después se detuvo
esa copia, conservando sus volúmenes, y se restauró lab02fase4.

## Recuperación tras el reinicio de Windows/WSL

La rama y todos los archivos modificados sobrevivieron; no se descartó trabajo.
Docker Desktop necesitó reactivar su integración con WSL. Con varias copias
antiguas activas se observaron 4,7 GiB ocupados de 5,6 GiB y swap de 2 GiB llena.
Eso demuestra presión de memoria, sin confirmar la causa del bloqueo original.
Se detuvieron únicamente copias de este laboratorio y se conservaron sus datos;
el otro laboratorio no se modificó.

Límites: Airflow 1792 MiB, API 512 MiB, MLflow 1024 MiB, bootstrap 768 MiB y
cada PostgreSQL 256 MiB. Bootstrap finaliza antes de Airflow. Una tarea/parser/
worker web, hilos numéricos acotados; build del producto una sola vez. MLflow
iniciaba procesos auxiliares innecesarios; MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false
redujo consumo observado a unos 355 MiB. Airflow estabilizado aproximadamente
en 1,12 GiB, API 213 MiB y PostgreSQL 23–31 MiB cada uno. No se modificaron
permisos del host ni configuración global de Python/WSL.

## Pruebas reproducibles y alcance

- Suite pytest completa con advertencias como errores y PostgreSQL real:
  **122 passed in 11.18s**, sin pruebas omitidas. Ocho casos SQL. Contratos
  independientes de MLflow vivo.
- Nuevas pruebas: unión y precedencia temporal, promociones ausentes, hash
  determinista, candidato peor/fallido, recuperación sin reentrenar ni
  sobrescribir champion más reciente, resultados SQL inmutables, bloqueos de
  envío, 503 administrativos y estados terminales.
- scripts/verify_airflow.py: DAG real, promoción, no promoción, reintento/fallo,
  caídas, recarga y persistencia.
- scripts/verify_airflow_details.py: configuración/estados reales, seis datasets
  en MLflow y caída de PostgreSQL de Airflow.
- scripts/verify_cold_start.py: importación/entrenamiento automáticos desde vacío.
- Compose validado; pip check sin incompatibilidades. Datos originales verificados
  contra las 18 huellas conservadas de Fase 3. Secretos y salidas en outputs/,
  ignorado; evidencias públicas únicamente agregadas y revisadas.

Pendiente Fase 5: simulación final de varios días/cambios de demanda, revisión de
entrega desde clon/tag y tag entrega-lab2 tras aprobación. Las ventanas conservadoras
de 60 días para calibración/validación se mantienen; sin suficiente validación
futura respecto al vigente, el DAG informa no promoción. No se promete mejora
de costo para observaciones futuras no conocidas. No se avanzó a Fase 5.
