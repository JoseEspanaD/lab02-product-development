# Plan del Laboratorio 2 — NovaMercado

## Alcance y estado

Preparación realizada el 2026-11-14. Fuente oficial: instrucciones_lab.pdf,
7 páginas leídas, incluido el anexo completo. Modelado, API y persistencia implementados por fases.
Cada fase requiere autorización expresa; no comenzar la siguiente por iniciativa propia.

Estado: repositorio público configurado y main actualizado. PR #1 integrado. Fase 2 implementada en fase-2-api-persistencia, pendiente de
revisión y aprobación de merge. No iniciar Fase 3.
La terminal requiere elevación para Git, GitHub y descargas; se solicitará
para cada operación bloqueada. No se han cambiado permisos del sistema.

## Requisitos obligatorios y verificación

| Requisito | Evidencia prevista |
|---|---|
| FastAPI + modelos Pydantic; limpieza en módulos separados | pytest de contrato y limpieza sin MLflow activo |
| Políticas generales reparar/advertir/rechazar, no solo E01–E10 | Casos oficiales, límites, tipos erróneos, ambigüedades y reglas documentadas |
| Predicciones con versión de modelo y cantidad entera no negativa | Validación de todas las respuestas |
| PostgreSQL del producto, separado del de Airflow | Integración y volúmenes persistentes |
| Registrar solicitudes, predicciones, correcciones y observaciones | Consultas SQL, incluidos rechazos y reintentos |
| Observaciones idempotentes | Reenvío idéntico guarda 0; modificación cuenta solo filas cambiadas |
| Baseline y al menos un ML que lo mejore | Backtest temporal reproducible, métricas técnicas y de costo |
| Sugerencias coherentes con costos por familia | Costo faltante/sobrante y calibración por familia |
| MLflow: experimentos, modelos, linaje y alias vigente | Runs con datos/parámetros/métricas, versiones y alias |
| DAG Airflow usa histórico y observaciones | Ejecución disparada por API, datos nuevos incluidos |
| Promoción automática con criterio explícito | Casos de candidato mejor, peor y fallo |
| Recarga sin reinicio en <=120 s tras fin del DAG | Prueba cronometrada sobre versión realmente servida |
| Un comando docker compose up; servicio llamado mlflow | Arranque limpio siguiendo README |
| Bootstrap automático solo cuando hace falta | Primera carga/entrenamiento y segundo arranque sin repetición |
| Imágenes con versiones fijas; datos y secretos externos | Inspección de imágenes, Compose y archivos públicos |
| API usa modelo cargado durante caída de MLflow | Predicción exitosa, health degradado en <60 s y recuperación en <120 s |
| Arranque listo y cada reentrenamiento <=10 min | Tiempos medidos sin contar build |
| README, DECISIONES, contexto del agente, evidencias y tag | Revisión final desde clon limpio de entrega-lab2 |

Costo = costo_faltante * max(real - sugerido, 0)
      + costo_sobrante * max(sugerido - real, 0).

## Contrato completo a preservar

Puerto 8000; fecha canónica AAAA-MM-DD. Rechazos: HTTP 422 con detail explicativo.
Campos adicionales permitidos; nunca omitir ni renombrar campos obligatorios.

- POST /v1/prediccion: tienda_id, fecha, familias[{familia_id,en_promocion}].
  HTTP 200: tienda_id, fecha, version_modelo (texto),
  predicciones[{familia_id,venta_esperada,cantidad_sugerida}], calidad.
  cantidad_sugerida entero >=0. Se permiten solicitudes repetidas para una fecha.
- calidad: estado = ok | corregido | advertencia; observaciones =
  [{campo,accion,detalle}], accion = reparar | advertir. Si hay advertir,
  prevalece advertencia; ok implica lista vacía.
- POST /v1/observaciones: tienda_id, fecha, ventas[{familia_id,ventas}].
  HTTP 200: registros_guardados y calidad. Contar filas nuevas o modificadas;
  repetición idéntica: 200, registros_guardados=0.
- POST /admin/reentrenar: sin cuerpo; 202 con id de texto, o 503 si no inicia.
- GET /admin/reentrenar/{id}: estado = en_curso | exitoso | fallido.
  Al terminar incluir promovido, version (vigente al terminar) y motivo.
  ID desconocido: 404.
- GET /modelo: nombre, alias, version, todos de texto; describir modelo cargado.
- GET /health: 200 con estado=ok cuando API, DB, MLflow, Airflow y modelo
  funcionan; 200 con estado=degradado y motivo ante dependencia caída.
  Sin modelo cargado: 503.

## Auditoría de data/ (sin modificación)

- historico_ventas.csv: 83 052 filas; fecha, tienda_id, familia_id, ventas,
  en_promocion. 2024-03-01 a 2026-02-28, 730 fechas, 10 tiendas, 12 familias.
- 120 series: 108 con 730 días y 12 con 351. Tienda 10 abre 2025-03-15.
  Cobertura diaria exacta desde apertura, sin huecos ni filas previas a apertura.
- Sin vacíos, duplicados exactos, claves fecha/tienda/familia duplicadas ni
  referencias desconocidas. Ventas: enteras, 0–3479 (139 ceros);
  promociones: enteras, 0–19; sin negativos en el histórico.
- tiendas.csv: 10 filas, ciudad/departamento/tipo/fecha_apertura; tres formatos.
- familias.csv y costos.csv: 12 filas cada uno; catálogos compatibles.
- feriados.csv: 61 eventos, 2024-03-28 a 2026-12-31; ámbitos nacional,
  Antigua Guatemala, Cobán y Guatemala. Unión por fecha y ciudad exacta;
  ausencia de fila no implica dato faltante. No deducir cobertura completa
  del calendario a partir de la primera fecha de evento.
- Dos JSON válidos y diez de errores; E09 es idéntico a la observación válida.
  E10 combina "50,0" y "1,292", formatos que requieren política de ambigüedad.
- Los ejemplos usan 2025-11-17, dentro del histórico. No rechazarlos por el reloj
  ni por asumir que toda petición debe ser posterior al máximo del histórico.
- Las observaciones llegan antes de las predicciones del día siguiente y no
  incluyen promociones. Hay que conservar las promociones de las solicitudes.

## Arquitectura mínima propuesta

Un paquete Python con módulos de API, esquemas, limpieza, persistencia,
features, entrenamiento y acceso al modelo. Un DAG importa ese mismo código.
Sin frontend, Kubernetes, cola externa, feature store ni microservicios adicionales.

Docker Compose:
- api: FastAPI, puerto 8000; un proceso con modelo en memoria y sincronización
  periódica en segundo plano, sin bloquear endpoints con llamadas a MLflow.
- postgres: base del producto con volumen; tablas de catálogos/histórico,
  solicitudes y cambios de calidad, predicciones, observaciones y ejecuciones.
  Puede alojar también una base separada para metadatos MLflow.
- mlflow: tracking y Registry; artefactos persistentes, alias champion.
- airflow: despliegue mínimo con LocalExecutor y componentes mínimos exigidos
  por la versión elegida; sin Redis ni Celery.
- airflow-db: PostgreSQL propio, independiente del producto, con volumen.
- bootstrap: tarea finita con bloqueo/idempotencia; cargar datos y registrar
  primer modelo automáticamente; evitar carreras con arranque/reentrenamiento.

Datos originales como bind mount de solo lectura. Artefactos, caché del modelo
activo y bases en volúmenes. .env fuera de Git; .env.example sin secretos.
Identidad de cada modelo y preprocesado viajan juntos en el artefacto.
Revisar alias cada 30 s con timeout; cargar candidato antes del intercambio
atómico. Conservar último modelo utilizable ante fallo. health consulta estado
reciente de dependencias; recuperación no exige reinicio.

Modelo inicial propuesto: baseline estacional por tienda/familia/día semanal y
un regresor de árboles global sencillo (scikit-learn) con calendario, tienda,
familia, promociones, eventos locales/nacionales y estadísticas pasadas.
Probar primero un único candidato acotado, sin búsqueda extensa.
Predecir media no negativa; calibrar cantidad con cuantiles de residuos por
familia, q=c_faltante/(c_faltante+c_sobrante), redondeando a entero >=0.
Usar validación temporal para elegir y demostrar mejora, nunca prometerla sin
medición. Si no mejora, ajustar únicamente con autorización de la fase vigente.

## Fases y puertas de salida

### Fase 0 — Preparación (esta solicitud)

Entorno, auditoría, documentos y repositorio público con commit inicial en main.
Repositorio público y commit inicial confirmados; datos, PDF y secretos excluidos.

### Fase 1 — Modelado (fase-1-modelado)

Carga validada, features compartidas sin fuga, baseline, candidato, evaluación
cronológica y sugerencias por costo. Dependencias solo al necesitarlas.
Verificar MAE/RMSE y costo total/por familia sobre fechas retenidas; mejorar al
baseline. Medir entrenamiento; tests de corte temporal, apertura y feriados.
Registrar decisiones, semilla y huellas de datos, sin publicar filas originales.

Progreso: carga validada, features temporales compartidas, baseline estacional,
HistGradientBoostingRegressor, calibrador por costo, CLI de evaluación y pruebas.
Evaluación final: 7 080 filas de enero–febrero 2026; costo 307 713,40 -> 195 030,00
(-36,62 %); mejora en ambas mensualidades y las 12 familias. MAE 59,72 -> 39,47;
RMSE 111,12 -> 72,51. Entrenamiento ML aproximadamente 1,4 s en este equipo.
Resultados y protocolo en RESULTADOS_FASE1.md. Pruebas: 25 casos sintéticos,
con advertencias tratadas como errores. Verificación Git/push/PR al cerrar fase.
No se implementó ningún componente de la Fase 2 ni de infraestructura.


### Fase 2 — API y persistencia (fase-2-api-persistencia)

Contrato completo, normalización fuera de endpoints, PostgreSQL e idempotencia.
Usar adaptadores falsos del modelo/administración en unit tests; integración con DB.
Verificar todos los códigos y campos, E01–E10 y errores adicionales, concurrencia
al reenviar observaciones y conteos nuevos/modificados. Guardar promociones.

Progreso: seis endpoints del anexo, modelos Pydantic, limpieza independiente,
inferencia con modelo real de Fase 1 y repositorio PostgreSQL transaccional.
Solicitudes originales/limpias y calidad auditadas; predicciones repetidas y
promociones preservadas; observaciones idempotentes con upsert y conteo de cambios.
80 pruebas aprobadas con PostgreSQL real y sin MLflow/Airflow. Ejemplos E01–E10
verificados; inferencia real dentro y después del histórico. No se publica un
Registry ni un DAG ficticio: administración devuelve 503/404 hasta conectarlos.
Prueba de reinicio del PostgreSQL de pruebas y detalles en RESULTADOS_FASE2.md.


### Fase 3 — MLflow y contenedores (fase-3-mlflow-docker)

Tracking, linaje y alias; Docker Compose, datos externos, bootstrap y caché/recarga.
Verificar arranque vacío y segundo arranque, persistencia, imágenes fijas y
predicción durante caída de MLflow con tiempos de health y recuperación.
La salud integral solo podrá validarse por completo al integrar Airflow.

### Fase 4 — Reentrenamiento (fase-4-airflow)

DAG, disparo y consulta administrativos, corte temporal reproducible, uso de
observaciones y promociones registradas, promoción y recarga automáticas.
Verificar 202/503/404, estados finales, fallo y no promoción sin afectar vigente,
modelo nuevo servido <=120 s; DAG <=10 min. Evitar entrenamientos simultáneos.

### Fase 5 — Verificación y entrega (fase-5-entrega)

Simular varios días, datos defectuosos nuevos, observaciones corregidas,
reentrenamiento, caída de MLflow y reinicio sin borrar volúmenes.
README final, DECISIONES y evidencias sanitizadas de runs/versiones/DAG/respuestas.
Desde clon limpio: docker compose up y health ok <=10 min (sin build).
PR final; tras aprobación y merge, crear entrega-lab2 desde main final.

## Flujo Git obligatorio

Antes de cada fase autorizada: actualizar main con pull --ff-only y crear rama
nueva desde main. Commits descriptivos durante la fase; al terminar ejecutar sus
pruebas, push y PR hacia main con resumen y resultados reales.
Esperar aprobación explícita para merge y autorización separada de siguiente fase.
Conservar ramas locales y remotas después del merge; no usar --delete-branch.
No desarrollar directamente en main. Excepción: commit inicial de planificación.
