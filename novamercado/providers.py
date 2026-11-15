"""Adaptadores reemplazables por MLflow y Airflow en las fases siguientes."""

from dataclasses import dataclass
from threading import RLock
from typing import Protocol

import pandas as pd
from threadpoolctl import threadpool_limits

from .costs import CostCalibrator
from .features import build_features
from .models import SalesRegressor
from .schemas import ModelInfo, Prediction, RunStatus


class Unavailable(RuntimeError):
    pass


class ModelProvider(Protocol):
    def info(self) -> ModelInfo | None: ...
    def predict(self, request, history) -> tuple[ModelInfo, list[Prediction]]: ...


class Administration(Protocol):
    def start(self) -> str: ...
    def status(self, run_id: str) -> RunStatus | None: ...
    def dependencies(self) -> dict[str, bool]: ...


class DisconnectedAdministration:
    def start(self):
        raise Unavailable("Airflow todavía no está conectado")

    def status(self, run_id):
        return None

    def dependencies(self):
        return {"MLflow": False, "Airflow": False}


@dataclass
class Bundle:
    model: SalesRegressor
    calibrator: CostCalibrator
    info: ModelInfo


class LocalModelProvider:
    """ML real de Fase 1 con corte anterior al pronóstico, nunca un éxito simulado.

    Modo local de Fase 2: entrena/calibra desde CSV, guarda un bundle en memoria.
    El Registry, almacenamiento del artefacto y recarga pertenecen a Fase 3.
    """

    def __init__(self, data):
        self.data = data
        self.bundle = None
        self.cutoff = None
        self.lock = RLock()

    def info(self):
        with self.lock:
            return self.bundle.info if self.bundle else None

    def prepare(self, cutoff):
        cutoff = min(pd.Timestamp(cutoff), self.data.history.fecha.max() + pd.Timedelta(days=1))
        with self.lock:
            if self.bundle and self.cutoff == cutoff:
                return
            h = self.data.history[self.data.history.fecha < cutoff]
            calibration_start = cutoff - pd.Timedelta(days=60)
            train = h.fecha < calibration_start
            calibration = ~train
            families = set(self.data.families.familia_id)
            if (h.empty or not train.any() or not calibration.any()
                    or set(h.loc[train, "familia_id"]) != families
                    or set(h.loc[calibration, "familia_id"]) != families):
                raise Unavailable("Historia insuficiente anterior a la fecha para entrenar y calibrar")
            x = build_features(h, h, self.data.stores, self.data.holidays)
            with threadpool_limits(limits=2):
                model = SalesRegressor().fit(x.loc[train], h.loc[train, "ventas"].to_numpy())
                predicted = model.predict(x.loc[calibration])
            calibrator = CostCalibrator.fit(h.loc[calibration, "familia_id"],
                                             h.loc[calibration, "ventas"].to_numpy(),
                                             predicted, self.data.costs)
            info = ModelInfo(nombre="novamercado_hist_gradient_boosting", alias="local",
                             version=f"local-{cutoff.date()}-{self.data.hashes['historico_ventas.csv'][:8]}")
            self.bundle = Bundle(model, calibrator, info)
            self.cutoff = cutoff

    def predict(self, request, history):
        with self.lock:
            self.prepare(request.fecha)
            rows = pd.DataFrame([{"fecha": request.fecha, "tienda_id": request.tienda_id,
                                  "familia_id": f.familia_id, "en_promocion": f.en_promocion}
                                 for f in request.familias])
            x = build_features(history, rows, self.data.stores, self.data.holidays)
            with threadpool_limits(limits=2):
                expected = self.bundle.model.predict(x)
            suggested = self.bundle.calibrator.suggest(rows.familia_id, expected)
            return self.bundle.info, [Prediction(familia_id=f, venta_esperada=float(y),
                                                 cantidad_sugerida=int(q))
                                      for f, y, q in zip(rows.familia_id, expected, suggested)]
