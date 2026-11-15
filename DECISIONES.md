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
