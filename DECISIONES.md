# Decisiones técnicas y de producto

1. **Un paquete y Compose** en lugar de servicios de features/colas adicionales:
   reduce piezas sin eliminar FastAPI, PostgreSQL, MLflow ni Airflow obligatorios.
2. **Modelado global y baseline estacional** frente a 120 modelos especializados:
   compartir señal y mantener entrenamiento bajo diez minutos. Elegir tras backtest.
3. **Validación cronológica y corte por fecha solicitada**, frente a split aleatorio:
   ventas del día no están disponibles. Filtrar también histórico al atender ejemplos
   dentro de él. Separar ajuste, calibración y evaluación; no calibrar con test.
4. **Cantidad por costo asimétrico**: cuantil objetivo c_faltante/(c_faltante+
   c_sobrante), calibrado con residuos y convertido a entero no negativo.
   Comparar costo con baseline sobre las mismas fechas; verificar calibración.
5. **Promoción propuesta**: costo total estrictamente menor que el vigente en
   una ventana temporal común, con candidato entrenado sin esa ventana, métricas
   finitas y contrato válido. Registrar ambos costos, fechas y motivo en MLflow.
   Si no hay suficientes datos nuevos/validación, no promover y explicar por qué.
6. **Modelo local y refresco en segundo plano** en lugar de consultar Registry en
   cada predicción: seguir operando durante caída de MLflow; intercambio atómico.
7. **Observaciones con clave fecha/tienda/familia**, upsert transaccional y conteo
   de cambios reales; reenvío idéntico no cambia ni duplica ventas. Auditoría de
   solicitudes separada para conservar también reintentos y correcciones.
8. **Promociones**: unir observaciones con peticiones registradas de esa fecha;
   ante varias solicitudes usar regla determinista documentada (propuesta: última
   válida). Si faltan promociones no asumir cero silenciosamente: excluir esas
   filas del entrenamiento supervisado que las requiera y registrar cobertura.

## Política inicial de entradas (propuesta para fase 2)

Las transformaciones se informan en calidad; Pydantic valida después de limpiar.
No usar coerciones silenciosas. Ante cualquier rechazo devolver 422 con detail.

| Caso | Política propuesta y razón |
|---|---|
| E01 | Reparar texto de dígitos o T + dígitos si identifica tienda del catálogo |
| E02 | Reparar mayúsculas, tildes, espacios y nombres exactos del catálogo normalizados; sin coincidencia difusa |
| E03 | Reparar texto numérico inequívoco o decimal integral; rechazar fracciones, negativos, booleanos y no finitos |
| E04 | Reparar ISO a medianoche o DD/MM/AAAA bajo regla explícita; rechazar fecha inválida y hora no compatible |
| E05 | Rechazar lista incompleta: no inventar promociones para familias omitidas |
| E06 | Duplicados idénticos: deduplicar e informar; distintos: rechazar por conflicto |
| E07 | Reparar alias documentado tienda -> tienda_id solo si no hay conflicto; otros obligatorios ausentes: rechazar |
| E08 | Rechazar ventas negativas; no convertir devoluciones en demanda cero |
| E09 | Aceptar idempotentemente con registros_guardados=0 |
| E10 | Reparar coma decimal inequívoca como 50,0; rechazar 1,292 por ambigüedad decimal/miles |

Reglas generales adicionales: rechazar tienda/familia desconocida, listas vacías,
campos obligatorios ausentes, estructuras incorrectas, NaN/inf y valores fuera
del dominio. Campos extra sin efecto pueden ignorarse con advertencia explícita;
un alias en conflicto se rechaza. No recortar valores altos solo por superar el
máximo histórico. No usar la fecha actual como límite. Políticas concretas y
pruebas se consolidarán en la fase autorizada; no constituyen código implementado.


## Fase 1 — decisiones implementadas

- Un candidato global `HistGradientBoostingRegressor` (150 iteraciones, 31 hojas,
  learning_rate=0.08, l2=1, semilla 42), sin búsqueda de hiperparámetros. Objetivo:
  error cuadrático sobre ventas, estimación de media condicional. Salida recortada
  a cero. Frente a modelos por serie, aprovecha todas las tiendas/familias y
  entrena en aproximadamente 1,4 s. No se necesita una GPU.
- Baseline: media de hasta cuatro ventas del mismo día semanal (lags 7,14,21,28),
  fallback media de los 28 días anteriores y cero si no hay historia. Es dinámico:
  incorpora las observaciones disponibles cada día. Se calibra por costo igual
  que el ML para no favorecer artificialmente al candidato.
- Features: tienda, familia, ciudad y formato como categóricas; promociones del
  día recibidas, día semanal/mes/día del mes, seno/coseno anual, edad de tienda,
  indicadores de eventos nacionales y locales, lag7, medias7/28, estacional y
  cantidad de días observados en 28 días. No se usan ventas del día ni futuras.
- El encoder se ajusta solo con entrenamiento. Las categorías desconocidas
  usan -1 (missing en el estimador); la validación comercial de catálogos en
  solicitudes corresponde a la futura API. No se escala para árboles.
- `build_features` es compartida entre entrenamiento e inferencia; recibe
  historia y solicitudes por separado. Ignora ventas en solicitudes y obtiene
  promociones de estas. Reindexa por días calendario, nunca por número de filas.
  Huecos no son ceros observados, y se excluyen ventas anteriores a apertura.
  Funciona sin consultar la fecha del sistema.
- Split fijado antes de medir: entrenamiento hasta 2025-10-31; calibración en
  noviembre–diciembre 2025; evaluación en enero–febrero 2026. Modelo fijo durante
  calibración y evaluación. Las features de cada fecha se actualizan con ventas
  anteriores, reproduciendo el orden diario descrito por el PDF. Los residuos
  de calibración son fuera de entrenamiento y el test no ajusta parámetros.
- Cuantiles por familia de `(real-predicho)/(predicho+1)` en calibración; el +1
  evita dividir por cero y el residuo relativo comparte señal entre tiendas de
  distinta escala. q=c_faltante/(c_faltante+c_sobrante). Sugerencia = redondear
  max(0, predicho+(predicho+1)*cuantil). Es una aproximación de la distribución
  condicional; el redondeo al entero más cercano puede desviarse del óptimo
  discreto exacto. Se mide su costo real, no se presume optimalidad universal.
- No se reentrena con calibración/test tras reportar resultados. No se exporta
  un binario a Git. Las clases de modelo/calibrador son reutilizables para su
  empaquetado posterior; MLflow y el ciclo de producción quedan pendientes.
- requirements.txt fija versiones directas y transitivas realmente instaladas
  en .venv. Solo NumPy, pandas, scikit-learn, threadpoolctl (límite de hilos) y
  pytest se usan directamente; el resto son sus dependencias. Wheels cp314
  instalados y pruebas exitosas confirman funcionamiento en Python 3.14.4.
- Resultados: costo -36,62 %, mejor MAE/RMSE y menor costo en las 12 familias.
  Ver RESULTADOS_FASE1.md. Un único bloque de test de dos meses no demuestra
  desempeño durante todo un año ni ante el cambio de demanda desconocido.

Las decisiones de políticas de entradas y promoción de modelos de las secciones
anteriores siguen siendo propuestas para fases posteriores; no se implementaron.

## Fase 2 — API, limpieza y persistencia implementadas

Esta sección consolida las políticas implementadas y prevalece sobre propuestas
iniciales de las fases posteriores. No se implementaron Registry, DAG ni Compose.

- **Contrato:** modelos Pydantic de entradas canónicas y respuestas; FastAPI expone
  los seis endpoints exactos. La limpieza vive en cleaning.py; API delega a Service.
  OpenAPI incluye los cuerpos canónicos aunque primero se recibe el cuerpo crudo
  para auditar también JSON inválido, claves repetidas y rechazos.
- **E01–E04:** reparar tienda con dígitos o prefijo T/t, nombre/ID de familia
  normalizado sin tildes/mayúsculas/espacios, promociones textuales o decimales
  integrales, DD/MM/AAAA e ISO exactamente a medianoche sin zona. No interpretar
  horas distintas ni convertir zonas horarias suponiendo un día comercial.
- **E05–E07:** predicción requiere todas las familias del catálogo (las diez tiendas
  del dataset venden las doce). Duplicado idéntico se elimina con corrección;
  distinto se rechaza. Alias tienda -> tienda_id solo si no se envían ambos;
  ambos presentes se rechazan aunque sus valores coincidan. Otros obligatorios
  ausentes se rechazan. Campos adicionales se ignoran con advertencia explícita.
- **E08–E10:** rechazar ventas negativas y booleanos; observación idéntica produce
  200 y cero cambios. Números de texto con coma y una/dos cifras decimales se
  reparan; tres cifras tras coma, miles o formatos ambiguos se rechazan. Texto
  decimal con punto se admite. Ventas fraccionarias finitas no negativas se
  admiten: el anexo no exige que sean enteras. Promociones sí deben ser enteras.
- **Dominios generales:** rechazar JSON no objeto, lista vacía, campos repetidos,
  NaN/inf, referencias desconocidas, fechas inválidas/preapertura, tipos incorrectos
  y valores negativos. Guardarraíl numérico técnico de 1e15 para entradas; no se
  recortan valores ni se impone el máximo observado en el histórico. El límite
  evita cantidades no representables con seguridad en el cálculo/almacenamiento.
  No se utiliza la fecha del sistema como criterio de validez.
- **Observaciones parciales:** se aceptan subconjuntos no vacíos de familias
  conocidas, sin completar ventas ausentes. Una solicitud es atómica: cualquier
  elemento inválido rechaza todo el envío. Permite correcciones puntuales sin
  reemplazar las demás familias.
- **Auditoría:** solicitudes guarda texto original, cuerpo canónico, calidad con
  campo/acción/detalle, HTTP y motivo de rechazo. Correcciones están en JSONB
  dentro de la misma solicitud, sin una tabla adicional. Predicciones almacena
  cada familia, promociones, resultados y versión, vinculada a la solicitud.
  No se deduplican pronósticos: cada petición aceptada crea un registro nuevo.
- **Idempotencia SQL:** observaciones tiene PK (fecha, tienda_id, familia_id).
  INSERT ON CONFLICT DO UPDATE ... WHERE ventas IS DISTINCT FROM ... RETURNING
  cuenta solo filas nuevas o modificadas. Transacción única con su auditoría;
  orden de familias estable evita inversión de bloqueos entre envíos concurrentes.
  Los reintentos se auditan aunque no cambien las observaciones.
- **Acceso SQL:** psycopg parametrizado sin ORM; conexiones cortas, timeout de
  conexión 2 s y consultas 5 s. PostgreSQL es obligatorio, sin fallback a SQLite.
  El esquema del producto no usa la DB de Airflow. Catálogos/histórico siguen en
  CSV read-only durante esta fase; carga persistente/bootstrap corresponde a Fase 3.
- **Historia y promociones:** para inferencia se consulta solo observaciones con
  fecha anterior; prevalecen sobre histórico para esa clave. Promociones originales
  se conservan por pronóstico; la consulta recupera la del mayor solicitud_id por
  fecha/tienda/familia. Sin pronóstico previo queda NULL, nunca cero inventado.
  La Fase 4 decidirá qué filas sin promociones excluir del entrenamiento.
- **ML local real:** adaptador LocalModelProvider reutiliza SalesRegressor,
  build_features y CostCalibrator. Al atender fechas dentro del histórico entrena
  y calibra solo con fechas estrictamente anteriores; para las posteriores usa
  el corte fin del histórico +1. Calibración separada de 60 días, no reusa test
  para ajustar hiperparámetros. Mantiene un bundle en memoria protegido con lock.
  Los últimos 28 días bastan para las features de una solicitud; se descarta
  historia anterior innecesaria antes de reindexar, sin modificar las fórmulas.
- **Versión y disponibilidad:** alias local y versión local-FECHA-HASH describen el
  modelo cargado, sin fingir Registry. /modelo devuelve 503 sin modelo, al igual
  que /health. Con modelo y DB pero sin MLflow/Airflow, health devuelve 200
  degradado explicando esas dependencias. Errores SQL devuelven 503 sin revelar
  credenciales, DSN ni SQL. Si DB está caída no puede persistirse esa petición:
  se informa fallo y no se responde con un éxito sin auditoría.
- **Administración:** interfaces inyectables para modelo y administración.
  Adaptador desconectado: POST reentrenar 503 y GET ID desconocido 404. El contrato
  contempla 202/en_curso/exitoso/fallido, verificado con dobles explícitos; la app
  local no crea ejecuciones ni promociones ficticias.
- **Pruebas:** contratos con repositorio en memoria explícito y modelos de prueba;
  integración SQL con PostgreSQL 16.11 en contenedor/volumen exclusivo. También se
  verificó la API con modelo real, ejemplos del docente y DB; resultados agregados
  y límites en RESULTADOS_FASE2.md. Python existente 3.14.4, sin cambiar versión.
  Starlette instalado utiliza httpx2 para TestClient; se retiró httpx obsoleto del
  entorno y se fijaron las dependencias realmente utilizadas en requirements.txt.

Referencias de implementación: [validación y errores de FastAPI](https://fastapi.tiangolo.com/tutorial/handling-errors/),
[transacciones psycopg](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)
y [adaptación JSONB](https://www.psycopg.org/psycopg3/docs/basic/adapt.html).

## Fase 3 — MLflow, Compose y bootstrap implementados

- **Cuatro servicios:** API y bootstrap comparten una imagen Python 3.14.4 con
  dependencias fijadas; PostgreSQL 16.11 del producto y servicio llamado exactamente
  mlflow con imagen 3.17.2. No añadir Airflow ni su DB hasta Fase 4. No hacen falta
  Redis, MinIO, otra DB de tracking ni un servidor de inferencia separado.
- **MLflow:** backend SQLite y artefactos en su propio volumen. Registry soportado
  sobre backend SQL, un worker y un único escritor del alias bajo lock PostgreSQL.
  Elegido frente a otro servicio PostgreSQL porque este volumen basta para el lab.
  El producto sigue persistiendo en PostgreSQL; SQLite no sustituye sus tablas.
- **Linaje:** experimento novamercado-ventas; MAE/RMSE y costo de baseline, candidato
  y vigente; cortes, conteos, hiperparámetros, semilla, SHA-256 de requisitos y los
  cinco CSV, entradas dataset de MLflow sin filas originales y snapshot del código
  en el artefacto. SOURCE_REVISION es opcional; en pruebas se registró working-tree,
  sin atribuir un commit inexistente. El código exacto queda junto al modelo.
- **Artefacto:** ForecastArtifact contiene estimador, encoder, calibrador y cortes.
  Se registra con flavor sklearn y firma de features/salidas, sin input_example
  de datos originales. Cloudpickle explícito evita añadir skops para serializar
  el objeto compuesto. Deserialización habilitada solo para el Registry propio
  configurado; API valida clase, esquema, calibración, familias y hashes antes de
  intercambiar. La interfaz sigue separando construcción de features e inferencia.
- **Primer corte:** validación de 60 días hasta 2025-11-16, calibración en los 60
  anteriores, entrenamiento previo. El bundle es aplicable desde 2025-11-17,
  incluyendo el efecto de selección por validación. Permite el ejemplo oficial
  histórico sin fuga temporal. Se eligió frente a entrenar con todo el histórico,
  que no podría atender ese ejemplo sin usar datos futuros. Los demás datos
  publicados sí están disponibles como historia de features, siempre filtrados
  por la fecha solicitada; no se utilizan para ajustar este primer bundle.
- **Selección posterior:** nueva validación posterior a la selección del vigente;
  candidato y vigente se comparan en las mismas filas, sin ajustar con esa ventana.
  Requiere métricas finitas no negativas y costo estrictamente menor que baseline
  y vigente. Empates no promueven. MAE/RMSE se registran, sin exigir que mejoren:
  la función objetivo de decisión es el costo asimétrico del negocio.
- **Promoción:** entrenamiento y registro bajo lock de sesión PostgreSQL común a
  todos los escritores. Se guarda el run, métricas, linaje y versión; se descarga
  y valida el artefacto; solo entonces se cambia champion. No se realizan escrituras
  ni consultas de auditoría posteriores al alias. Cerrar la sesión libera el lock.
  Errores previos, candidato peor o fallo de promoción conservan el vigente.
  La API además rechaza un alias apuntado manualmente a una versión no elegible.
- **Bootstrap:** carga atómica de catálogos y 83 052 filas a PostgreSQL con hashes.
  Si existen datos se utiliza el snapshot; si existe champion no se ajusta ni
  registra nada. Incluso sin originales disponibles puede reutilizar lo persistido.
  Ante fallo entre registro y alias, recupera la versión elegible ya registrada,
  sin repetir ajuste. Versiones rechazadas no se activan ni vuelven a entrenarse
  automáticamente. Importación completa o rollback; nunca reemplazar el snapshot
  publicado silenciosamente. El COPY inicial tiene timeout de 120 s.
- **API sin red para inferir:** RegisteredModelProvider conserva bundle en memoria
  y volumen local. Refresco cada 10 s en hilo independiente, con timeouts acotados
  y sin reintentos prolongados. Descarga y caché atómica antes de cambiar el puntero;
  no mantener el lock de inferencia durante llamadas externas. Error de red, disco,
  artefacto inválido o alias no elegible conserva tanto memoria como caché previas.
- **Salud:** la disponibilidad MLflow incluye resolver/sincronizar su alias. Su
  estado caduca tras 45 s sin comprobación reciente; una caída no bloquea predicción.
  Sin modelo se responde 503. Sin Airflow, health sigue 200 degradado incluso tras
  recuperar MLflow: no afirmar el ok integral que aún no puede comprobarse.
- **Volúmenes y secretos:** postgres_data, mlflow_data y model_cache independientes.
  Originales montados read-only solo durante bootstrap; API usa datos PostgreSQL.
  .dockerignore es una lista de inclusión de código/configuración de build; no
  pasan datos, .env, credenciales, .git, pruebas ni outputs al contexto. Usuario
  sin privilegios para API/bootstrap. Variables reales permanecen fuera de Git.
- **Validación:** suite local/SQL sin servidor MLflow para contratos, prueba de
  serialización MLflow en filesystem y script de integración sobre Compose real.
  Se comprobaron promoción, rechazo de alias, fallo de trabajo, interrupción,
  recarga, caché y reinicio de todos los servicios sin borrar volúmenes.
  Dos avisos internos conocidos de MLflow 3.17 (tipos de chat Any y codecs.open
  obsoleto en Python 3.14) se filtran solo en el test de serialización; no se
  silencian advertencias del código del proyecto ni se cambió Python.

Pendiente Fase 4: DAG, estado/disparo real administrativos y unión de histórico
con observaciones/promociones para reentrenar. train_and_register ya es una
función reutilizable; la prueba de Fase 3 le pasó el snapshot publicado. No se
presenta ese trabajo manual de integración como una ejecución de Airflow.

Referencias: [Registry y aliases de MLflow](https://www.mlflow.org/docs/latest/ml/model-registry/workflow/)
y [servidor y artefactos](https://www.mlflow.org/docs/latest/tracking/server/).

## Fase 4 — Airflow y reentrenamiento

- Airflow 2.11.1-python3.12, API REST estable v1 y autenticación Basic interna.
  LocalExecutor con scheduler/webserver en un servicio supervisado; una sola
  instancia evita añadir broker y workers. PostgreSQL 16.11 independiente.
- Runtime de entrenamiento Python 3.14.4 copiado de la imagen del producto,
  aislado mediante PYTHONHOME/LD_LIBRARY_PATH. Evita instalar versiones ML
  distintas dentro de Airflow y deserializar bundles con librerías incompatibles;
  no cambia el Python local ni instala dependencias globales.
- Programación bajo demanda: el PDF exige disparo por API, no un cron. schedule=None,
  catchup=False, max_active_runs=1 y bloqueo común de escritores de modelo.
  POST concurrentes reutilizan ejecución activa bajo otro bloqueo SQL de envío.
- Una tarea de entrenamiento/evaluación/promoción comparte los módulos existentes;
  finalizador all_done conserva fallo del DAG y resultado consultable. Reintento
  único, demora 10 s, timeout de tarea 4 min y de DAG 9 min, bajo límite de 10 min.
- Corte derivado de ventas disponibles y promociones, jamás del reloj ni de la
  logical_date de Airflow. Correcciones prevalecen sobre histórico. Promociones
  provienen de última solicitud; fallback a promoción publicada para correcciones
  históricas. Sin ambas, excluir etiqueta y registrar cobertura, sin asumir cero.
- Linaje operacional adicional: hash de histórico unido con observaciones, filas
  usadas/excluidas, último día e id de ejecución; dataset metadata en MLflow sin
  filas originales. Los hashes de publicación del bundle permanecen estables
  para verificar compatibilidad con catálogos de la API.
- Resultado inmutable por run_id en producto; ejecución/estado real en Airflow.
  Reintento después de registrar recupera la versión por execution_id, verifica
  artefacto y vigente previo antes de promover; resultado guardado evita repetir
  una ejecución completada. Un resultado exitoso sin datos nuevos no crea modelo.
- La promoción conserva costo estrictamente menor que baseline/vigente, ventanas
  comunes futuras y artefacto validado. Escritura de resultado posterior al alias
  es recuperable por tags de Registry; un fallo SQL no obliga a repetir ajuste.
- /health verifica DB y scheduler Airflow y DAG no pausado; las llamadas externas
  tienen timeout. Predicción nunca consulta Airflow y mantiene modelo cargado
  durante fallos del orquestador/Registry.

Referencias oficiales: [REST API Airflow 2.11.1](https://airflow.apache.org/docs/apache-airflow/2.11.1/stable-rest-api-ref.html),
[DAGs y programación](https://airflow.apache.org/docs/apache-airflow/2.11.1/core-concepts/dags.html)
y [Docker Airflow](https://airflow.apache.org/docs/apache-airflow/2.11.1/howto/docker-compose/).

### Recuperación tras reinicio de WSL

Se conservaron la rama y todos los cambios. No hay evidencia persistida que
confirme OOM como causa del bloqueo. WSL dispone de aproximadamente 5,6 GiB RAM.
Se fijan límites por servicio: Airflow 1792 MiB, API 512 MiB, MLflow 1024 MiB,
bootstrap 768 MiB y cada PostgreSQL 256 MiB. Bootstrap termina antes de arrancar
Airflow; solo una tarea, parser y worker web, hilos numéricos a uno. El build
se declara solo en API y Airflow para evitar construir copias del mismo producto.
No se modifican permisos, configuración de WSL ni volúmenes del usuario.

MLflow 3.17.2 activa por defecto un ejecutor de trabajos auxiliares con varios
procesos, detectado durante la prueba. Se configura
MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false porque este producto solo necesita
tracking/Registry/artefactos y Airflow ejecuta el entrenamiento. Evita consumir
memoria en funciones ajenas al laboratorio. El límite inicial de 640 MiB causó
un reinicio; se amplió a 1024 MiB antes de desactivar esos procesos.
Referencia: [variables oficiales MLflow](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.environment_variables.html).
