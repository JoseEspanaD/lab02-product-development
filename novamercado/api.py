"""FastAPI: adaptadores de persistencia, modelo y administración inyectables."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
import pandas as pd
import psycopg

from .cleaning import Cleaner, Rejected, parse_json
from .data import KEY, load_data
from .providers import DisconnectedAdministration, LocalModelProvider, Unavailable
from .repository import PostgresRepository
from .schemas import (Health, ModelInfo, ObservationInput, ObservationOutput,
                      PredictionInput, PredictionOutput, RunStarted, RunStatus)


class Service:
    def __init__(self, data, repository, model, administration):
        self.data, self.repository, self.model = data, repository, model
        self.administration = administration
        self.cleaner = Cleaner(data)

    def process(self, raw, observation=False):
        endpoint = "/v1/observaciones" if observation else "/v1/prediccion"
        try:
            parsed, quality = self.cleaner.clean(parse_json(raw), observation)
        except Rejected as exc:
            self.repository.rejected(endpoint, raw, str(exc))
            raise HTTPException(422, detail=str(exc)) from exc
        if observation:
            saved = self.repository.save_observation(raw, parsed, quality)
            return ObservationOutput(registros_guardados=saved, calidad=quality)
        day = pd.Timestamp(parsed.fecha)
        historical = self.data.history[self.data.history.fecha < day]
        observed = self.repository.observations_before(parsed.fecha)
        observed["fecha"] = pd.to_datetime(observed.fecha)
        # Una corrección operativa tiene precedencia sobre la fila histórica.
        history = pd.concat([historical, observed], ignore_index=True).drop_duplicates(KEY, keep="last")
        try:
            info, predictions = self.model.predict(parsed, history)
        except Unavailable as exc:
            self.repository.rejected(endpoint, raw, str(exc), status=503,
                                     parsed=parsed, quality=quality)
            raise HTTPException(503, detail=str(exc)) from exc
        result = PredictionOutput(tienda_id=parsed.tienda_id, fecha=parsed.fecha,
                                  version_modelo=info.version, predicciones=predictions, calidad=quality)
        self.repository.save_prediction(raw, parsed, result)
        return result


def create_app(data, repository, model, administration=None):
    service = Service(data, repository, model, administration or DisconnectedAdministration())
    @asynccontextmanager
    async def lifespan(app):
        if hasattr(model, "start"):
            model.start()
        try:
            yield
        finally:
            if hasattr(model, "stop"):
                await run_in_threadpool(model.stop)
    app = FastAPI(title="NovaMercado", version="0.3.0", lifespan=lifespan)
    app.state.service = service

    @app.exception_handler(psycopg.Error)
    async def database_error(request, exc):
        # No exponer DSN, credenciales ni SQL en la respuesta.
        return JSONResponse(status_code=503, content={"detail": "PostgreSQL del producto no disponible"})

    @app.post("/v1/prediccion", response_model=PredictionOutput)
    async def prediction(request: Request):
        return await run_in_threadpool(service.process, await request.body())

    @app.post("/v1/observaciones", response_model=ObservationOutput)
    async def observations(request: Request):
        return await run_in_threadpool(service.process, await request.body(), True)

    @app.post("/admin/reentrenar", status_code=202, response_model=RunStarted)
    def retrain():
        try:
            return RunStarted(id=service.administration.start())
        except Unavailable as exc:
            raise HTTPException(503, detail=str(exc)) from exc

    @app.get("/admin/reentrenar/{id}", response_model=RunStatus, response_model_exclude_none=True)
    def run_status(id: str):
        try:
            status = service.administration.status(id)
        except Unavailable as exc:
            raise HTTPException(503, detail=str(exc)) from exc
        if status is None:
            raise HTTPException(404, detail="Ejecución desconocida")
        return status

    @app.get("/modelo", response_model=ModelInfo)
    def model_info():
        info = service.model.info()
        if info is None:
            raise HTTPException(503, detail="No hay modelo cargado")
        return info

    @app.get("/health", response_model=Health, response_model_exclude_none=True)
    def health(response: Response):
        if service.model.info() is None:
            response.status_code = 503
            return Health(estado="degradado", motivo="No hay modelo cargado")
        dependencies = {"PostgreSQL": service.repository.healthy(),
                        **service.administration.dependencies()}
        missing = [name for name, ok in dependencies.items() if not ok]
        return Health(estado="degradado", motivo="No disponible: " + ", ".join(missing)) if missing else Health(estado="ok")

    # Documentar entradas canónicas sin ocultar el paso previo de limpieza.
    original_openapi = app.openapi

    def openapi():
        schema = original_openapi()
        for path, model_type in [("/v1/prediccion", PredictionInput),
                                 ("/v1/observaciones", ObservationInput)]:
            body = model_type.model_json_schema(ref_template="#/components/schemas/{model}")
            schema["components"]["schemas"].update(body.pop("$defs", {}))
            schema["paths"][path]["post"]["requestBody"] = {
                "required": True, "content": {"application/json": {"schema": body}}}
        return schema

    app.openapi = openapi
    return app


def local_app():
    """uvicorn novamercado.api:local_app --factory --port 8000."""
    data = load_data(os.environ.get("DATA_DIR", "data"))
    repository = PostgresRepository(os.environ["DATABASE_URL"])
    model = LocalModelProvider(data)
    model.prepare(data.history.fecha.max() + pd.Timedelta(days=1))
    return create_app(data, repository, model)


def registered_app():
    from .registry import Registry
    from .registered_provider import RegisteredModelProvider
    repository = PostgresRepository(os.environ["DATABASE_URL"])
    data = repository.load_data()
    registry = Registry(os.environ["MLFLOW_TRACKING_URI"], os.environ.get("MODEL_NAME", "novamercado"),
                        os.environ.get("MODEL_ALIAS", "champion"))
    provider = RegisteredModelProvider(data, registry, os.environ.get("MODEL_CACHE_DIR", "/cache"))
    from .airflow_client import AirflowAdministration
    administration = AirflowAdministration(provider, repository,
        os.environ.get("AIRFLOW_URL", "http://airflow:8080"),
        os.environ["AIRFLOW_USERNAME"], os.environ["AIRFLOW_PASSWORD"])
    return create_app(data, repository, provider, administration)
