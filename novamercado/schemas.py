"""Contrato canónico: la limpieza explícita ocurre antes de validarlo."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonnegativeInt = Annotated[int, Field(strict=True, ge=0)]
NonnegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Correction(Contract):
    campo: str
    accion: Literal["reparar", "advertir"]
    detalle: str


class Quality(Contract):
    estado: Literal["ok", "corregido", "advertencia"] = "ok"
    observaciones: list[Correction] = Field(default_factory=list)


class Promotion(Contract):
    familia_id: str
    en_promocion: NonnegativeInt


class Sale(Contract):
    familia_id: str
    ventas: NonnegativeFloat


class PredictionInput(Contract):
    tienda_id: Annotated[int, Field(strict=True, gt=0)]
    fecha: date
    familias: Annotated[list[Promotion], Field(min_length=1)]


class ObservationInput(Contract):
    tienda_id: Annotated[int, Field(strict=True, gt=0)]
    fecha: date
    ventas: Annotated[list[Sale], Field(min_length=1)]


class Prediction(Contract):
    familia_id: str
    venta_esperada: NonnegativeFloat
    cantidad_sugerida: NonnegativeInt


class PredictionOutput(Contract):
    tienda_id: int
    fecha: date
    version_modelo: str
    predicciones: list[Prediction]
    calidad: Quality


class ObservationOutput(Contract):
    registros_guardados: NonnegativeInt
    calidad: Quality


class ModelInfo(Contract):
    nombre: str
    alias: str
    version: str


class RunStarted(Contract):
    id: str


class RunStatus(Contract):
    estado: Literal["en_curso", "exitoso", "fallido"]
    promovido: bool | None = None
    version: str | None = None
    motivo: str | None = None

    @model_validator(mode="after")
    def terminal_fields(self):
        if self.estado != "en_curso" and any(
            value is None for value in [self.promovido, self.version, self.motivo]
        ):
            raise ValueError("La ejecución terminada requiere promovido, version y motivo")
        return self


class Health(Contract):
    estado: Literal["ok", "degradado"]
    motivo: str | None = None
