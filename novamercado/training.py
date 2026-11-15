"""Ajuste, calibración y comparación temporal compartidos por bootstrap y futuros jobs."""

from dataclasses import dataclass, field
from time import perf_counter

import numpy as np
import pandas as pd
from sklearn.utils.validation import check_is_fitted
from threadpoolctl import threadpool_limits

from .costs import CostCalibrator, metrics
from .features import CATEGORICAL, NUMERIC, build_features
from .models import SalesRegressor, SeasonalBaseline


@dataclass
class ForecastArtifact:
    model: object
    calibrator: CostCalibrator
    available_from: str
    calibration_end: str
    dataset_hashes: dict = field(default_factory=dict)

    def predict(self, x):
        expected = self.model.predict(x)
        suggested = self.calibrator.suggest(x.familia_id, expected)
        return pd.DataFrame({"venta_esperada": expected, "cantidad_sugerida": suggested}, index=x.index)

    def validate(self):
        if not isinstance(self.model, SalesRegressor):
            raise ValueError("Estimador registrado no compatible")
        check_is_fitted(self.model.pipeline)
        if list(self.model.pipeline.feature_names_in_) != CATEGORICAL + NUMERIC:
            raise ValueError("Esquema de features incompatible")
        if not self.calibrator.adjustments or not np.isfinite(list(self.calibrator.adjustments.values())).all():
            raise ValueError("Calibración no válida")
        if pd.Timestamp(self.calibration_end) >= pd.Timestamp(self.available_from):
            raise ValueError("Corte temporal inconsistente")


def promotion_decision(candidate, baseline, incumbent=None):
    for result in [candidate, baseline, *([incumbent] if incumbent is not None else [])]:
        if any(not np.isfinite(result[k]) or result[k] < 0
               for k in ["mae", "rmse", "costo_total", "costo_medio"]):
            return False, "Métricas inválidas"
    if candidate["costo_total"] >= baseline["costo_total"]:
        return False, "No reduce estrictamente el costo del baseline"
    if incumbent is not None and candidate["costo_total"] >= incumbent["costo_total"]:
        return False, "No reduce estrictamente el costo del vigente"
    return True, "Costo estrictamente menor en la misma validación temporal"


def train_candidate(data, validation_end, incumbent=None, calibration_days=60, validation_days=60):
    started = perf_counter()
    end = pd.Timestamp(validation_end)
    if end > data.history.fecha.max():
        raise ValueError("La validación debe estar cubierta por observaciones reales")
    validation_start = end - pd.Timedelta(days=validation_days - 1)
    calibration_start = validation_start - pd.Timedelta(days=calibration_days)
    h = data.history[data.history.fecha <= end].reset_index(drop=True)
    train = h.fecha < calibration_start
    calibration = (h.fecha >= calibration_start) & (h.fecha < validation_start)
    validation = h.fecha >= validation_start
    if any(not mask.any() for mask in [train, calibration, validation]):
        raise ValueError("Historia insuficiente para las tres particiones")
    if incumbent is not None and pd.Timestamp(incumbent.available_from) > validation_start:
        raise ValueError("Se requiere validación posterior a la selección del vigente")
    x = build_features(h, h, data.stores, data.holidays)
    y = h.ventas.to_numpy(dtype=float)
    results, artifacts = {}, {}
    with threadpool_limits(limits=2):
        for name, model in [("baseline", SeasonalBaseline()), ("candidate", SalesRegressor())]:
            model.fit(x.loc[train], y[train])
            calibrator = CostCalibrator.fit(h.loc[calibration, "familia_id"], y[calibration],
                                             model.predict(x.loc[calibration]), data.costs)
            artifact = ForecastArtifact(model, calibrator, str((end + pd.Timedelta(days=1)).date()),
                                        str((validation_start - pd.Timedelta(days=1)).date()), data.hashes)
            artifacts[name] = artifact
            output = artifact.predict(x.loc[validation])
            results[name] = metrics(y[validation], output.venta_esperada, output.cantidad_sugerida,
                                     h.loc[validation, "familia_id"], data.costs)
        if incumbent is not None:
            output = incumbent.predict(x.loc[validation])
            results["incumbent"] = metrics(y[validation], output.venta_esperada, output.cantidad_sugerida,
                                           h.loc[validation, "familia_id"], data.costs)
    eligible, reason = promotion_decision(results["candidate"], results["baseline"], results.get("incumbent"))
    artifacts["candidate"].validate()
    report = {"metrics": results, "eligible": eligible, "reason": reason,
              "splits": {name: {"start": str(h.loc[mask, "fecha"].min().date()),
                                 "end": str(h.loc[mask, "fecha"].max().date()), "rows": int(mask.sum())}
                         for name, mask in [("train", train), ("calibration", calibration), ("validation", validation)]},
              "hashes": data.hashes, "features": CATEGORICAL + NUMERIC,
              "seconds": perf_counter() - started}
    return artifacts["candidate"], report, x.loc[validation].iloc[:1]
