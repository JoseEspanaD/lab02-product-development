# Decisiones propuestas — pendientes de implementación y validación

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
