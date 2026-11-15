# Verificación integral y entrega — Fase 5

Fase 5 desarrollada en fase-5-verificacion-entrega desde main aa3f27b.
Estado de cierre: PR #1–#5 confirmados integrados en main; PR #5 fusionado en
472e657. El usuario autorizó el cierre documental y el tag anotado entrega-lab2.
Relectura completa de las siete páginas de instrucciones_lab.pdf, incluido el
anexo, y revisión de AGENTS, PLAN, DECISIONES, README y resultados de Fases 1–4.
El PDF y los datos permanecen locales. Código funcional ensayado desde el clon
limpio del commit 40c0b4b; los commits posteriores documentan las evidencias.

**Resultado: 50 verificaciones cumplidas, 1 parcial y 0 incumplidas: 98,04 %.**
La única parcial es el criterio compuesto de tag/plazo: la referencia de entrega
es entrega-lab2 sobre main final, pero el plazo no puede verificarse sin la fecha
límite oficial. No se declara cumplimiento temporal.
Las 50 verificaciones funcionales/documentales de la matriz están respaldadas
por las pruebas indicadas; esto no es una nota oficial ni una garantía de costo futuro.

## Método y evidencias

- **U:** suite `.venv/bin/python -m pytest -q -W error`, PostgreSQL real aislado:
  127 pruebas aprobadas, sin omisiones, 20,42 s. Once casos de persistencia:
  diez con PostgreSQL y uno de indisponibilidad. Contrato sin
  depender de MLflow/Airflow vivos. tests/test_api.py y test_official_examples.py
  comprueban campos, tipos, errores generales y E01–E10; test_postgres.py usa SQL
  real, transacciones, concurrencia, auditoría y bloqueos. Se revalidaron después
  los dos casos de candidato peor/fallido conservando IDs distintos de vigente y candidato.
- **T:** tests/test_features.py, test_data_temporal.py, test_local_provider.py y
  test_registry_provider.py verifican fechas anteriores, apertura, lags por
  calendario, equivalencia lote/día, promociones, particiones y selección sin fuga.
- **M:** dos ejecuciones independientes de novamercado.evaluate, outputs locales
  fase5_evaluacion_1.json y fase5_evaluacion_2.json. Iguales métricas totales,
  por mes y familia; tiempos excluidos de la comparación de igualdad.
- **C:** clon limpio local, seis servicios, proyecto exclusivo lab02fase5verificado;
  API 18006, MLflow 15006, Airflow 18086. Nuevos volúmenes, nueva .env, datos
  docentes colocados en data/, sin .venv dentro del clon ni pasos de carga/ajuste
  manual. Build secuencial separado del cronómetro. verify_cold_start.py.
- **A:** verify_airflow.py y verify_airflow_details.py sobre ese proyecto:
  DAG/REST/Registry/SQL reales, promoción, rechazo por ventana insuficiente,
  entrenamiento fallido, reintentos, inferencia concurrente, recarga, caídas,
  DB Airflow, recuperación y persistencia tras down/up sin -v.
- **E:** verify_delivery.py: cinco días, tiendas 1 y 10, observaciones sintéticas
  con cambio de escala, envíos repetidos/corregidos, entradas defectuosas nuevas,
  ventas futuras que no cambian predicción anterior, reinicio offline de API
  usando caché, caída y recuperación de PostgreSQL del producto.
- **S:** revisión Git/imágenes, .gitignore/.dockerignore, hashes de los 18
  archivos docentes, versiones fijadas y pip check. Solo evidencia agregada
  pública; JSON completos y logs quedan en outputs/ ignorado.

## Matriz completa del PDF

C = cumplido con evidencia; P = parcial/pendiente; I = incumplido.
La numeración desglosa 51 verificaciones con igual peso, no representa una nota
oficial ni garantiza desempeño en datos ocultos. Los detalles del anexo se
comprueban por separado de los requisitos generales.

| ID | Página | Requisito | Estado | Evidencia concreta |
|---|---:|---|:---:|---|
| 01 | 1 | Pronóstico diario por tienda/familia con venta y cantidad | C | U, E; api.py, schemas.py, registered_provider.py |
| 02 | 1 | Reparar, advertir o rechazar e informar acción/motivo | C | U, E; cleaning.py; políticas en DECISIONES |
| 03 | 1 | Registrar predicciones y ventas reales con versión | C | U, A; solicitudes/predicciones/observaciones en repository.py |
| 04 | 1 | Mejora automática con criterio y uso sin reinicio manual | C | A; DAG, Registry y refresco de API |
| 05 | 2 | Costo faltantes/sobrantes exactamente según costos.csv | C | U test_cost_formula_and_metrics; M; costs.py |
| 06 | 2 | Solo ventas anteriores; promociones de la solicitud | C | T, E; features.py, observations_before; promociones persistidas |
| 07 | 2 | Fechas simuladas sin validar con reloj del sistema | C | U, T, E; Cleaner usa apertura/calendario; DAG usa fechas del snapshot |
| 08 | 2 | FastAPI y contrato Pydantic | C | U; api.py y schemas.py; OpenAPI comprobado |
| 09 | 2 | Limpieza en módulos con pruebas fuera de endpoints | C | U; cleaning.py y Service.process |
| 10 | 2 | Política explícita general, más allá del catálogo | C | U, E; formatos, ambigüedad, extras, duplicados, Unicode y dominios |
| 11 | 2 | Versión textual en toda predicción | C | U, E; version_modelo y registro SQL |
| 12 | 2 | pytest de contrato sin MLflow activo | C | U; TestClient con dobles inyectados, sin red al Registry |
| 13 | 3 | PostgreSQL del producto en Docker separado de Airflow | C | C, A, E; dos servicios, DSN y volúmenes distintos |
| 14 | 3 | Guardar solicitudes, correcciones, predicciones y observaciones | C | U consultas SQL; auditoría original/canónica/calidad/estado; E |
| 15 | 3 | Observaciones idempotentes | C | U concurrente y E; upsert WHERE IS DISTINCT FROM |
| 16 | 3 | Conservar información al detener/levantar | C | A; SQL, resultados de ejecuciones, Registry, caché y bootstrap reutilizados |
| 17 | 3 | Baseline sencillo y ML que lo mejore | C | M; SeasonalBaseline e HistGradientBoostingRegressor, costo -36,62 % |
| 18 | 3 | Métricas técnicas y de negocio | C | M y A; MAE/RMSE/costo total/medio, runs MLflow |
| 19 | 3 | Cantidad sugerida coherente con costos por familia | C | U; CostCalibrator, cuantil c_f/(c_f+c_s), no negativos/enteros |
| 20 | 3 | Experimentos, modelos y linaje en MLflow | C | A; runs, métricas, parámetros, artefacto y seis dataset inputs |
| 21 | 3 | Vigente mediante alias en Model Registry | C | A; novamercado@champion, versión registrada y servida |
| 22 | 3 | Criterio de reemplazo explícito y automatizado | C | U y A; costo estrictamente menor al baseline y vigente en ventana común |
| 23 | 3 | DAG usa histórico y observaciones de PostgreSQL | C | A; snapshot lógico, cobertura y hash en linaje; retraining.py |
| 24 | 3 | Disparar DAG mediante endpoint | C | A; POST 202 con dag_run_id real y duplicado activo reutilizado |
| 25 | 3 | Consultar estado real de cada ejecución | C | U, A; REST Airflow y resultado persistido; 404/503 |
| 26 | 3 | Modelo promovido usado <=120 s después del DAG | C | A; /modelo y predicciones; cota conservadora incluye DAG completo |
| 27 | 3 | Fallo/candidato no elegible conserva vigente | C | U candidato peor/empate/fallo; A fallo real/no ventana; inferencia continua |
| 28 | 3 | Todo con compose up; servicio exactamente mlflow | C | C desde clon; compose.yaml con seis servicios |
| 29 | 3 | Bootstrap sin modelo carga, entrena y registra solo | C | C; imported=true/trained=true/modelo 1 sin intervención |
| 30 | 3 | Segundo arranque conserva sin repetir bootstrap | C | A; imported=false/trained=false, mismos registros/versiones |
| 31 | 3 | Imágenes con versiones fijas | C | S; Python 3.14.4, PG 16.11, MLflow 3.17.2, Airflow 2.11.1 |
| 32 | 3 | Datos/credenciales fuera de imágenes y repositorio | C | S; whitelist Docker, montajes ro, env ignorada; inspección de imágenes |
| 33 | 3 | Incluir .env.example | C | S, C; plantilla sin claves reales, configuración suficiente |
| 34 | 3 | API sigue con modelo cargado ante caída MLflow | C | A y E; predicciones idénticas incluso reiniciando API offline |
| 35 | 3 | health detecta MLflow caído en <60 s | C | A, E; cronómetro monotónico, estado degradado con motivo |
| 36 | 3 | health vuelve a ok en <120 s al regresar MLflow | C | A, E; recuperación sin reinicio manual de API |
| 37 | 4 | Arranque integral health ok <=600 s, sin build | C | C; proyecto sin contenedores ni volúmenes previos |
| 38 | 4 | Cada reentrenamiento <=600 s | C | A; éxito, no promoción y fallo real acotados; DAG timeout 9 min |
| 39 | 4 | GitHub claro con código/config/DAG/Docker/tests/contexto | C | S; repositorio PUBLIC, AGENTS.md y estructura de módulos |
| 40 | 4 | README permite arranque desde cero e indica carpeta | C | C; data/, generación de claves solo con Docker, sin Python del host |
| 41 | 4 | DECISIONES cubre políticas/features/cantidad/promoción y alternativas | C | Documento revisado y ampliado; secciones por fase |
| 42 | 4 | Operación simulada: días, defectos, observaciones, DAG, caídas y reinicio | C | A y E; cambios sintéticos de escala, sin afirmar precisión en período oculto |
| 43 | 5 | Código completo API/modelo/DAG/Docker/pruebas y evidencia pública | C | S; archivos versionados y RESULTADOS_FASE1–5 con métricas/IDs/respuestas |
| 44 | 5 | Tag entrega-lab2 previo al plazo de entrega | P | Referencia entrega-lab2, tag anotado sobre main final autorizado; plazo no verificable sin fecha límite oficial |
| 45 | 6 | POST /v1/prediccion: campos exactos, 200, fecha ISO y cantidad entera >=0 | C | U y E; doce familias y versión, repetición permitida |
| 46 | 6 | calidad: estados/acciones/prioridad y lista vacía en ok | C | U test_warning_takes_precedence, casos válidos y corregidos; E |
| 47 | 6–7 | POST /v1/observaciones: contrato 200, conteo nuevos/modificados y reenvío 0 | C | U concurrente y E: 12 nuevos, 0 repetidos, 1 corregido |
| 48 | 7 | POST /admin/reentrenar sin cuerpo: 202 id texto o 503 | C | U, A; Airflow real, indisponibilidad sin éxito inventado |
| 49 | 7 | GET ejecución: estados, campos terminales, versión vigente y 404 | C | U, A; versión confirmada bajo lock; exitoso/fallido/no promoción |
| 50 | 7 | GET /modelo: nombre, alias, versión textuales del cargado | C | U, C, A, E; cambio observado sin reiniciar API |
| 51 | 6–7 | Puerto 8000; rechazo 422/detail; health 200 ok/degradado+motivo y 503 sin modelo | C | U; C/A/E por HTTP a puerto interno 8000; sin modelo probado en unitarias |

## Incumplimientos y huecos corregidos

1. Texto NUL/Unicode inválido podía fallar al auditar en PostgreSQL. Se rechaza
   antes de limpieza comercial con 422 y se audita; NUL literal se representa
   como texto escapado. Tres nuevas pruebas SQL; no se convierte en venta válida.
2. Versión terminal ante fallo podía ser la todavía cargada por la API, anterior
   al alias real. El trabajo confirma el vigente bajo model_lock antes de evaluar;
   se conserva para el finalizador. SQL impide cambiar un resultado terminado.
3. Un finalizador sin ejecución registrada podía terminar con código cero.
   Ahora termina con error; prueba explícita, sin simular éxito.
4. Evidencia de arranque vacío incompleta si quedaban volúmenes sin contenedores:
   se comprueban ambos. La prueba de promoción ahora exige promovido=true y
   comprueba inferencia HTTP 200 durante el trabajo.
5. Reiniciar Airflow podía dejar un PID obsoleto del webserver, que coincidía
   con otro proceso y bloqueaba la recuperación. La prueba real excedió 119 s
   y mantuvo health degradado. Se asigna un archivo PID temporal con UUID nuevo
   por arranque, sin borrar archivos ni volúmenes. Se repite la integración completa.
6. README requería .venv para generar claves aunque el clon no la contiene.
   Ahora basta Docker; los dos generadores se ejecutaron con la imagen fijada.

## Modelado reproducido con datos reales

Entrenamiento hasta 2025-10-31, calibración noviembre–diciembre de 2025,
evaluación enero–febrero de 2026: 7.080 filas. Mismo modelo fijo, features
actualizadas solo con ventas anteriores. Ni promociones ni etiquetas futuras
entran al ajuste/calibración o selección de un pronóstico anterior.

| Modelo | MAE | RMSE | Costo total |
|---|---:|---:|---:|
| Baseline estacional | 59,716314 | 111,118449 | 307713,40 |
| HistGradientBoostingRegressor | 39,465647 | 72,510545 | 195030,00 |

Reducción de costo **36,619595 %**. Las dos ejecuciones repitieron exactamente
las métricas totales, por familia y mes. La mejora se mantiene en las doce
familias y ambas mensualidades. El calibrador aprende cuantiles por familia
en un período separado; la cantidad es una aproximación medida al óptimo de
costo asimétrico, no una garantía universal.

## Integración final: mediciones

| Comprobación | Tiempo observado |
|---|---:|
| Arranque vacío integral, health=ok | 131.81 s |
| DAG con promoción, POST → terminal consultado | 31.96 s |
| Cota conservadora de recarga, incluyendo todo el DAG | 32.16 s |
| DAG sin ventana nueva, sin promoción | 18.64 s |
| DAG fallido con reintento | 61.00 s |
| Detección MLflow caído | 11.35 s |
| Recuperación MLflow | 11.46 s |
| Recuperación Airflow tras stop/start | 53.33 s |
| Recuperación PostgreSQL de Airflow | 62.07 s |
| Reinicio integral sin borrar volúmenes | 106.71 s |

La cota de recarga suma desde antes del POST hasta confirmar la nueva versión
servida: incluye entrenamiento, espera y sondeo, no solo la duración de un GET.
No se reinició la API para promover. Doce comprobaciones durante el DAG devolvieron
200. El fallo de Registry y la ejecución sin datos nuevos conservaron champion=2.
Después de down/up persistían doce observaciones y tres ejecuciones; sus resultados
seguían consultables y el modelo era el mismo. Los reinicios conservan volúmenes.

| Ejecución real Airflow | Estado final | Promovido | Versión |
|---|---|---|---|
| api__50bbed06296a4ccaaa9e2639d5aa8d12 | success | sí | 2 |
| api__359dfd6220d54f50afd9047714b332cc | success | no | 2 |
| api__b85373bc015b462481fcd15c2d3bcbbc | failed | no | 2 |

Run MLflow del candidato: `df45f730384a4b25a49e6b7735f89562`. Ambas tareas del DAG fallido
constan failed con try_number=2, evidencia del reintento. DAG bajo demanda,
max_active_runs=1 y dos tareas, comprobados en REST Airflow real.

MLflow contiene seis dataset inputs: cinco publicaciones y snapshot operacional,
12 observaciones recibidas/usadas, ninguna excluida por promociones. Validación
hasta 2026-03-01 sobre 7.092 filas. Esta ventana **incluye doce etiquetas sintéticas**
y se utiliza como prueba de promoción, separada del benchmark real anterior.

| Modelo en ese DAG | MAE | RMSE | Costo total |
|---|---:|---:|---:|
| Baseline | 59.6941 | 111.0543 | 308326.80 |
| Vigente v1 | 39.4076 | 72.3890 | 197243.90 |
| Candidato v2 | 39.6891 | 72.0310 | 195119.30 |

Se promovió por costo menor a ambos: MAE ligeramente peor frente al vigente es
compatible con el criterio explícito. El costo oculto futuro no puede inferirse
de las etiquetas sintéticas.

| Verificación adicional | Resultado |
|---|---:|
| Detección MLflow caído en simulación diaria | 9.07 s |
| Reinicio API con MLflow detenido, caché utilizable | 6.02 s |
| Recuperación MLflow en ese ensayo | 13.64 s |
| Recuperación PostgreSQL del producto | 2.50 s |

Cinco días (2026-03-02–06), tiendas 1 y 10: 120 observaciones nuevas, cada envío
repetido guardó cero y cada corrección de una familia guardó uno. Doce ventas
sintéticas futuras del 20 de marzo no cambiaron la predicción del 7 de marzo.
Sumadas a las doce del primer DAG quedan 144 observaciones, sin duplicados.
Los reenvíos de pronóstico sí quedan registrados por separado, con versión.

HTTP 422 comprobado para fecha imposible, tienda booleana, familias incompletas,
promoción fraccionaria y duplicado contradictorio. HTTP 200 con advertencia al
reparar T01, fecha DD/MM/AAAA, familia en mayúsculas y número textual, ignorando
un campo adicional. Extracto de esa respuesta real (la lista completa tiene
12 familias), no incluye filas docentes:

```json
{
  "tienda_id": 1,
  "fecha": "2026-03-07",
  "version_modelo": "2",
  "predicciones": [{"familia_id": "abarrotes", "venta_esperada": 872.9066208655785, "cantidad_sugerida": 1086}],
  "calidad": {"estado": "advertencia", "observaciones": [
    {"campo": "tienda_id", "accion": "reparar", "detalle": "Identificador convertido a entero"},
    {"campo": "fecha", "accion": "reparar", "detalle": "Fecha convertida a AAAA-MM-DD"},
    {"campo": "familias[0].familia_id", "accion": "reparar", "detalle": "Familia interpretada como abarrotes"},
    {"campo": "familias[0].en_promocion", "accion": "reparar", "detalle": "Número convertido al tipo canónico"},
    {"campo": "extra", "accion": "advertir", "detalle": "Campo adicional ignorado"}
  ]}
}
```

Se muestra una de las doce predicciones del cuerpo; no se renombra ningún
campo del contrato. Ejemplos completos de respuestas pequeñas observadas:

```json
{"detail": "familias[0].en_promocion: se requiere un entero"}
```
HTTP 422; sin inventar promociones.

```json
{"estado": "fallido", "promovido": false, "version": "2", "motivo": "Entrenamiento fallido; consultar logs de Airflow"}
```
HTTP 200 al consultar el DAG que falló con MLflow detenido.

```json
{"detail": "PostgreSQL del producto no disponible"}
```
HTTP 503 mientras su DB estaba detenida. MLflow/Airflow caídos sí permitieron
inferir con resultados idénticos; PG del producto caído impide auditar y no se
confirma éxito. Después de recuperar: HTTP 200 `{"estado":"ok"}` y modelo 2.

Conteos SQL al cerrar los ensayos:

| Tabla / condición | Filas |
|---|---:|
| historico | 83052 |
| datos_publicados | 5 |
| solicitudes | 94 |
| predicciones | 552 |
| observaciones | 144 |
| ejecuciones | 3 |
| rechazos_422 | 5 |


Registry conserva exactamente versiones 1 y 2, ambos runs FINISHED, champion=2.
Bootstrap del reinicio: `{"trained":false,"imported":false,"version":"2"}`.
No se entrenó ni registró de nuevo el modelo inicial. El guard de arranque vacío
rechazó además un proyecto ya usado, sin ejecutar up.

Las imágenes de API y Airflow fueron inspeccionadas sin data, .env, .git, outputs,
PDF o .venv del host. El historial y los archivos públicos se revisaron antes de publicar, sin
patrones de tokens/clave privada ni credenciales locales conocidas.
Las 18 huellas originales permanecen intactas; pip check no detectó incompatibilidad.
No se añadieron dependencias de producción ni cambió el algoritmo del modelo.

Sin OOM en API, Airflow ni MLflow. Airflow registró un reinicio automático durante
el ensayo de fallos de su DB y recuperó ok; no se presenta como cero reinicios.
Uso observado al cerrar: Airflow 1,00 GiB, API 224,5 MiB, MLflow 366,6 MiB, cada
PostgreSQL 16–34 MiB. Solo queda activo el proyecto verificado del laboratorio;
las copias anteriores están detenidas, con todos sus volúmenes conservados.
La aplicación del otro laboratorio no fue modificada. Antes de levantar otra
copia, detener la verificada: desde outputs/fase5-final, `docker compose stop`.


El primer ensayo de montaje usó enlaces que apuntaban fuera del contenedor y
falló con archivo ausente; fue corregido colocando archivos reales en data/.
Otro ensayo detectó el PID obsoleto y falló en recuperación. Ambos quedaron
detenidos, con volúmenes conservados; no se cuentan como pruebas aprobadas.
Las cifras anteriores proceden del nuevo proyecto lab02fase5verificado.


## Límites de la evidencia y cierre

- El período docente oculto no está disponible: no puede verificarse su costo,
  longitud ni demanda futura. Las observaciones sintéticas prueban integración,
  idempotencia y reacción operativa; no prueban precisión fuera del histórico.
- La política conserva ventanas de 60 días de calibración y validación; si no hay
  ventana futura suficiente respecto a la selección del vigente, responde exitoso
  sin promoción y explica por qué. No hay garantía de adaptación inmediata.
- Imágenes construidas y disponibles antes del cronómetro; no se midió la descarga
  desde un registry lento. Los tiempos corresponden a WSL (5,6 GiB); no garantizan
  los mismos tiempos en cualquier hardware. Se evitó ejecutar copias completas simultáneas. No se
  cambiaron permisos del host ni se borraron volúmenes.
- Ante caída del PostgreSQL del producto se devuelve 503: no puede confirmarse
  una predicción sin su auditoría. La caída de MLflow/Airflow sí mantiene inferencia.
- La prueba parte de un clon local limpio de la rama (sin heredar .venv, caches o
  modelos), no de un tag final. Los cinco PR están integrados y el remoto es público.
  El cierre solo modifica documentación y exclusiones; conserva las evidencias
  previas sin repetir las pruebas integrales. La referencia de entrega es el tag
  anotado entrega-lab2 sobre main final. El plazo oficial permanece sin verificar.
  El enlace al repositorio es el entregable al GES; no se accede al GES desde aquí.
