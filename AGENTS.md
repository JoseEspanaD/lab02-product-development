# Contexto y reglas del proyecto

Laboratorio 2 Product Development, NovaMercado. Autoridad de requisitos:
instrucciones_lab.pdf (7 páginas, incluido anexo). Ver PLAN.md para matriz,
contrato completo, auditoría, arquitectura y fases. Idioma: español.

## Alcance actual

Fase 1 autorizada: modelado y validación temporal, en fase-1-modelado.
No avanzar a la Fase 2 sin autorización expresa del usuario.
Trabajar una fase a la vez. No iniciar fase siguiente sin permiso.
No delegar a subagentes salvo petición expresa del usuario.
Priorizar Python sencillo, módulos pequeños y decisiones fáciles de explicar.
No omitir requisitos obligatorios para reducir complejidad.

## Entorno y datos

Raíz: /home/jose/lab02_pd; venv .venv, prompt lab02.
Activar con source .venv/bin/activate. Usar python -m pip desde el entorno.
Python local 3.14.4; versión de contenedores y dependencias por validar antes de
implementación. No instalar stack ML/MLOps hasta la fase que lo necesite.
No modificar originales de data/ ni publicar sus archivos, ejemplos o el PDF.
Nunca publicar .env, credenciales, tokens, dumps, modelos binarios o logs crudos.
Datos montados read-only; generados en rutas ignoradas/volúmenes.

## Invariantes técnicos

- FastAPI y Pydantic; limpieza fuera de endpoints, con pytest sin MLflow vivo.
- Cumplir campos, tipos, estados HTTP y calidad del anexo (ver PLAN.md).
- Fecha simulada: no validar contra reloj del sistema.
- Features y validación solo usan ventas de fechas anteriores a la predicha.
- Tienda 10 abre el 2025-03-15; no rellenar preapertura con ceros.
- Conservar promociones de peticiones: observaciones no las contienen.
- Persistir solicitudes, correcciones, predicciones/versiones y observaciones.
- PostgreSQL del producto separado del de Airflow; observaciones idempotentes.
- Baseline y ML mejorado medidos; métrica de costo además de métricas técnicas.
- MLflow con Registry/alias y linaje. Fallo/candidato peor conserva vigente.
- Recarga <=120 s; caída MLflow no interrumpe inferencia con modelo cargado.
- health degrada en <60 s, recupera <120 s; sin modelo HTTP 503.
- Arranque y DAG <=10 min, excluyendo build del tiempo de arranque.
- docker compose up inicia todo, bootstrap idempotente, servicio mlflow.
- Fijar versiones compatibles tras verificarlas; no usar latest.

## Git y colaboración

main es la rama estable. Solo el commit inicial de planificación se hace en main.
Antes de cada fase autorizada, actualizar main con git pull --ff-only y crear
una rama independiente fase-N-descripcion desde ese main actualizado.
Realizar commits descriptivos durante la fase. Al terminar, ejecutar las pruebas,
hacer push de la rama y crear un Pull Request hacia main con resumen y resultados.
Nunca hacer merge sin aprobación explícita del usuario.
Después del merge, conservar la rama tanto localmente como en GitHub; no usar
--delete-branch ni activar la eliminación automática de ramas.
No comenzar la fase siguiente sin autorización.
Tag entrega-lab2 solo desde commit final de main al finalizar laboratorio.
Antes de publicar, revisar archivos staged y exclusiones de datos/secretos.
No presentar comandos propuestos como ejecutados ni pruebas pendientes como aprobadas.
Documentar decisiones, alternativas y justificaciones en DECISIONES.md.
Si hay bloqueos de permisos o autenticación, informarlos; no eludir montajes
protegidos ni solicitar tokens por chat. No incluir credenciales en salidas.
