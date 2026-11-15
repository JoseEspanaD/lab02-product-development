# Laboratorio 2 — NovaMercado

Estado: preparación y análisis. El producto todavía no está implementado.
Ver [PLAN.md](PLAN.md), [AGENTS.md](AGENTS.md) y [DECISIONES.md](DECISIONES.md).

## Entorno local

```bash
cd ~/lab02_pd
source .venv/bin/activate
python --version
```

Entorno creado con `python3 -m venv --prompt lab02 .venv`, Python 3.14.4,
pip 25.1.1. No hay paquetes de aplicación instalados. La instalación auxiliar de
pypdf falló por DNS; el PDF se leyó extrayendo sus siete páginas con la biblioteca
estándar, sin modificarlo ni instalar dependencias adicionales.
La compatibilidad del stack y la versión Python de Docker se comprobarán en la
fase correspondiente; no asumir compatibilidad de Airflow con Python 3.14.

Los archivos docentes deben colocarse en `data/`, manteniendo su estructura.
No se publican ni se incorporarán a imágenes. `instrucciones_lab.pdf` también
se conserva solo localmente. Las instrucciones de ejecución con Docker se
incorporarán cuando exista y se verifique el producto.

## Flujo por fase

Solo tras autorización, actualizar main y crear la rama de fase correspondiente.
Al terminar: pruebas, commits descriptivos, push y PR con resultados reales.
Esperar aprobación antes del merge, conservar las ramas y solicitar autorización
antes de iniciar otra fase. El tag `entrega-lab2` se creará al final desde main.
