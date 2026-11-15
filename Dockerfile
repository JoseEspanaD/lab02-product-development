FROM python:3.14.4-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    GIT_PYTHON_REFRESH=quiet MLFLOW_DISABLE_AGENT_HINT=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --only-binary=:all: -r requirements.txt \
    && useradd --uid 10001 --create-home app \
    && mkdir /cache && chown app:app /cache
COPY novamercado ./novamercado
USER app
CMD ["python", "-m", "uvicorn", "novamercado.api:registered_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
