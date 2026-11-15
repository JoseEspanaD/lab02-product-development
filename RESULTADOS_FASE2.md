# Verificación de Fase 2

Rama: fase-2-api-persistencia. PR #1 confirmado MERGED antes de actualizar main
y crear esta rama. No se implementó infraestructura de la Fase 3.

## Suite automatizada

80 pruebas aprobadas con advertencias tratadas como errores, ejecutadas en el
entorno existente .venv (Python 3.14.4), contra PostgreSQL 16.11 real. Sin un
servidor MLflow ni Airflow. requirements.txt fija versiones instaladas;
`python -m pip check` no reporta incompatibilidades.

Comando reproducible, con TEST_DATABASE_URL configurada a una DB de pruebas:

```bash
.venv/bin/python -m pytest -q -W error
```

Las pruebas de contratos usan dobles explícitos. Las SQL crean esquemas únicos
en una DB aislada; no borran tablas ajenas ni datos originales. Sin DSN se omiten
cinco pruebas SQL; sin ejemplos docentes se omiten los diez casos E01–E10.

Cobertura comprobada:

- Seis rutas del anexo, códigos HTTP, campos, tipos y entradas canónicas OpenAPI.
- E01–E10 docentes, reparaciones, advertencias, prioridad de calidad y rechazos.
- JSON inválido/repetido/no finito, negativos, booleanos, fracciones en promociones,
  límites numéricos, catálogos desconocidos, fechas inválidas/preapertura y listas incompletas.
- Predicciones repetidas registradas por separado, con promociones y versión.
- Observaciones idénticas y modificadas, envíos parciales y conteo exacto.
- Ocho reenvíos concurrentes idénticos en PostgreSQL: una escritura de dos filas
  y siete resultados de cero cambios; los ocho envíos quedan auditados.
- Rollback ante fallo intermedio: ni solicitud exitosa ni predicciones parciales.
- Auditoría de original, canónico y correcciones incluso si el modelo devuelve 503.
- Historia estrictamente anterior, observaciones que corrigen filas históricas,
  selección determinista de promociones de solicitudes repetidas.
- Modelo ML real con corte anterior: cambiar ventas actuales/futuras no cambia
  el modelo ni la calibración que sirve un pronóstico previo.
- 503 sin modelo/DB/Airflow; estados administrativos completos mediante adaptador
  de pruebas, 404 desconocido y health degradado por dependencias desconectadas.

## Prueba integrada adicional con datos y modelo reales

TestClient de FastAPI + PostgreSQL aislado + LocalModelProvider, sin dobles de
modelo o repositorio:

| Comprobación | Resultado |
|---|---|
| health sin modelo | HTTP 503 |
| Ejemplo de pronóstico 2025-11-17 dentro del histórico | HTTP 200, 12 familias, local-2025-11-17-573c3e35 |
| Observaciones 2026-03-01 y reenvío idéntico | 12 y 0 registros guardados |
| Pronóstico 2026-03-02 posterior al histórico, dos solicitudes | HTTP 200, 12 familias, local-2026-03-01-573c3e35 |
| health con modelo y DB, sin MLflow/Airflow | HTTP 200 degradado y motivo explícito |
| POST reentrenar sin Airflow | HTTP 503, sin inventar una ejecución |

La prueba dejó 5 solicitudes, 36 predicciones y 12 observaciones. Se reinició
únicamente el contenedor lab02-fase2-postgres y se verificaron los mismos conteos
en su volumen persistente. No se borró el contenedor ni el volumen.

## Regresión del modelado

El recorte de lectura a los 28 días necesarios para las features no alteró las
métricas de Fase 1: baseline MAE 59,7163, RMSE 111,1184, costo 307 713,40;
ML MAE 39,4656, RMSE 72,5105, costo 195 030,00, mejora 36,62 %.

Todos los archivos originales conservan sus SHA-256 previos. Datos, PDF,
credenciales, entorno, archivos de configuración privados y salidas permanecen
ignorados por Git. `git diff --check` sin errores.

## Límites y pendientes

- PostgreSQL se probó en Docker de forma aislada; todavía no existe Compose.
- El modelo local se entrena/calibra en memoria; no existe Registry ni artefacto
  persistido y el reinicio de API repite ese ajuste. Fase 3 resolverá bootstrap,
  almacenamiento y carga/recarga del modelo registrado.
- Alias local y versión local-FECHA-HASH no afirman registro en MLflow.
- Se conserva solo el bundle local más reciente: consultas históricas de fechas
  diferentes pueden volver a entrenar; es un modo local de esta fase.
- Los adaptadores administrativos reales y los tiempos de recuperación del
  producto completo se comprobarán al conectar MLflow/Airflow. Nunca se comunica
  health ok mientras estén desconectados.
- No se puede auditar en PostgreSQL una solicitud durante una caída de esa misma
  DB; se responde 503 y no se confirma una escritura no persistida.
- El sandbox bloqueó conexiones Docker/PostgreSQL y una ejecución HTTP quedó
  bloqueada. Las pruebas completas y verificaciones reales se ejecutaron con
  permisos autorizados fuera de ese sandbox; no se cambiaron permisos del sistema.
