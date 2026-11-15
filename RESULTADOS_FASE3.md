# Resultados de Fase 3

Rama fase-3-mlflow-docker, creada desde main después de confirmar PR #2 MERGED.
Python local 3.14.4 en la .venv existente. No se implementó Airflow ni un DAG.

## Pruebas automatizadas

- **106 pruebas aprobadas**, con PostgreSQL real y sin servidor MLflow para el contrato.
- Comando: `.venv/bin/python -m pytest -q -W error`, con TEST_DATABASE_URL de pruebas.
- Dos filtros puntuales del test de serialización para avisos internos de MLflow
  3.17 (tipos de chat Any y codecs.open en Python 3.14). No se filtran avisos propios.
- `pip check` correcto y `git diff --check` sin errores.
- Originales verificados por SHA-256, sin cambios; no se publican filas ni secretos.

Incluye comparación estricta por costo, empates/no finitos, corte temporal,
validación sin ajuste de etiquetas retenidas, bootstrap sin reentrenar, recuperación
de registro sin alias, caché corrupta/no escribible, identidad de datasets,
refresco que no bloquea inferencia, fallos de ajuste/promoción, bloqueo SQL
exclusivo y snapshot transaccional e idempotente.

## Integración real de Compose

API, PostgreSQL 16.11, MLflow 3.17.2 y bootstrap en un proyecto de prueba aislado.
Imagen construida antes de medir el arranque. El script reproducible es
`scripts/verify_stack.py`; usa originales locales sin modificarlos y conserva volúmenes.

| Comprobación | Resultado |
|---|---|
| Arranque desde volúmenes vacíos | 44.80 s |
| Segundo arranque, sin build | 41.39 s |
| Trabajo posterior de entrenamiento, registro y promoción | 16.50 s |
| Cota conservadora de recarga, incluyendo todo ese trabajo | 16.51 s |
| Caída MLflow reflejada en health | 2.01 s (<60) |
| MLflow recuperado en health | 14.10 s (<120) |
| Predicción con MLflow detenido | 200, mismas cantidades y ventas esperadas |
| Reinicio de API mientras MLflow sigue detenido | 200 usando caché persistida, versión 2 |
| Alias movido a versión no elegible | API conserva versión 2 y se degrada |
| Trabajo sin ventana nueva de validación | Falla sin cambiar champion |
| Bootstrap con DATA_DIR inexistente tras primera carga | imported=false, trained=false, versión 2 |

La cota de recarga suma desde antes de empezar el entrenamiento hasta observar la
versión nueva. Es deliberadamente conservadora e incluye el ajuste, registro y
exec remoto; no se presenta el tiempo de una consulta HTTP como tiempo de recarga.
El alias se cambió y la API empezó a servir versión 2 sin reiniciarla.

**Health no llega a ok integral en esta fase:** antes y después de la caída queda
200 degradado por Airflow pendiente; durante la caída añade MLflow al motivo.
Arranque listo significa que los componentes de Fase 3 funcionan y hay modelo
cargado. El requisito final de health ok <=10 min se verificará en Fase 4.

## Tracking, Registry y modelos

- Experimento: novamercado-ventas. Dos runs terminados, con métricas y linaje.
- Cada run tiene metadatos de los cinco CSV, SHA-256, cortes y código del artefacto.
- Versión 1: bootstrap, validación 2025-09-18–2025-11-16, aplicable desde 2025-11-17.
- Versión 2: promoción real, validación 2025-12-31–2026-02-28, aplicable desde 2026-03-01.
- Versión 3: copia marcada no elegible para probar el guardarraíl de carga.
- Estado final: **novamercado@champion -> versión 2**. Versión 3 no está activa.

| Validación inicial (7 200 filas) | Baseline | Candidato |
|---|---:|---:|
| mae | 45.7825 | 38.9316 |
| rmse | 84.9113 | 70.1423 |
| costo_total | 229134.2000 | 195431.8000 |

| Validación posterior (7 200 filas comunes) | Baseline | Vigente v1 | Candidato v2 |
|---|---:|---:|---:|
| mae | 62.0190 | 40.4148 | 40.4599 |
| rmse | 118.7448 | 77.0465 | 77.2678 |
| costo_total | 323510.4000 | 205702.6000 | 203674.7000 |

La versión 2 reduce el costo frente al vigente aproximadamente 0,99 %. Su MAE/RMSE
son ligeramente peores: se promueve por el costo de negocio, criterio explícito.
Las ventanas son diferentes de la evaluación de Fase 1 y no se mezclan sus métricas.

## Persistencia

`down` seguido de `up`, sin borrar volúmenes, conservó exactamente:

| Tabla | Filas |
|---|---:|
| solicitudes | 10 |
| predicciones | 96 |
| observaciones | 12 |
| historico | 83052 |
| datos_publicados | 5 |

Conservó además dos runs, tres versiones y champion en 2. El segundo bootstrap
respondió `{"trained": false, "imported": false, "version": "2"}`.
También se comprobó reutilización con DATA_DIR apuntando a un directorio inexistente.
Imagen inspeccionada sin originales, .env, .git, outputs ni caché de modelos.
Credenciales reales en archivos locales ignorados; no están en la imagen.

## Pendientes y límites

- DAG, disparo y estado administrativo reales, unión de observaciones/promociones
  para reentrenar e integración con la DB independiente de Airflow: Fase 4.
- /admin/reentrenar sigue 503, sin ejecuciones ficticias.
- No afirmar salud integral ok mientras falte Airflow.
- Tiempos medidos en este equipo; el período oculto y el cambio de demanda se
  verificarán con la operación completa. No se usa reloj real para fechas simuladas.
- Solicitudes anteriores al corte de selección del modelo devuelven 503, evitando fuga temporal.
- El script de integración se corrigió para usar register_model al duplicar una
  versión negativa y se continuó desde checkpoint; las comprobaciones finales
  de fallo, recuperación y persistencia terminaron correctamente. No se borraron volúmenes.
