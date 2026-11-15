"""Sugerencias calibradas con costos asimétricos, independientes de la evaluación."""

from dataclasses import dataclass

import numpy as np
import pandas as pd


def business_cost(actual, suggested, shortage, surplus) -> np.ndarray:
    actual, suggested = np.asarray(actual, dtype=float), np.asarray(suggested, dtype=float)
    if not np.isfinite(actual).all() or not np.isfinite(suggested).all():
        raise ValueError("Valores no finitos")
    if (actual < 0).any() or (suggested < 0).any():
        raise ValueError("Ventas y sugerencias no negativas requeridas")
    shortage, surplus = np.asarray(shortage, dtype=float), np.asarray(surplus, dtype=float)
    if (not np.isfinite(shortage).all() or not np.isfinite(surplus).all()
            or (shortage <= 0).any() or (surplus <= 0).any()):
        raise ValueError("Costos positivos y finitos requeridos")
    return shortage * np.maximum(actual - suggested, 0) + surplus * np.maximum(suggested - actual, 0)


@dataclass
class CostCalibrator:
    adjustments: dict[str, float]

    @classmethod
    def fit(cls, families, actual, predicted, costs: pd.DataFrame):
        """Residuos relativos para compartir calibración entre tiendas de distinta escala."""
        predicted = np.asarray(predicted, dtype=float)
        actual = np.asarray(actual, dtype=float)
        families = list(families)
        if (actual.shape != predicted.shape or len(families) != len(actual)
                or (actual < 0).any() or (predicted < 0).any()
                or not np.isfinite(actual).all() or not np.isfinite(predicted).all()):
            raise ValueError("Calibración requiere valores alineados, finitos y no negativos")
        if not set(families).issubset(set(costs.familia_id)):
            raise ValueError("Familia sin costos")
        frame = pd.DataFrame({"familia_id": families,
                              "residuo": (actual - predicted) / (predicted + 1)})
        if not np.isfinite(frame.residuo).all() or frame.empty:
            raise ValueError("Calibración vacía o no finita")
        adjustments = {}
        for row in costs.itertuples():
            if (not np.isfinite([row.costo_faltante, row.costo_sobrante]).all()
                    or row.costo_faltante <= 0 or row.costo_sobrante <= 0):
                raise ValueError("Costos positivos requeridos")
            residuals = frame.loc[frame.familia_id == row.familia_id, "residuo"]
            if residuals.empty:
                raise ValueError(f"Sin calibración para {row.familia_id}")
            q = row.costo_faltante / (row.costo_faltante + row.costo_sobrante)
            adjustments[row.familia_id] = float(np.quantile(residuals, q))
        return cls(adjustments)

    def suggest(self, families, predicted) -> np.ndarray:
        predicted = np.asarray(predicted, dtype=float)
        if not np.isfinite(predicted).all() or (predicted < 0).any():
            raise ValueError("Predicción no negativa y finita requerida")
        adjustment = np.asarray([self.adjustments[f] for f in families])
        return np.rint(np.maximum(0, predicted + (predicted + 1) * adjustment)).astype(np.int64)


def metrics(actual, predicted, suggested, families, costs: pd.DataFrame) -> dict:
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    rates = costs.set_index("familia_id").loc[list(families)]
    cost = business_cost(actual, suggested, rates.costo_faltante.to_numpy(),
                         rates.costo_sobrante.to_numpy())
    return {"filas": len(actual), "mae": float(np.mean(np.abs(actual - predicted))),
            "rmse": float(np.sqrt(np.mean((actual - predicted) ** 2))),
            "costo_total": float(cost.sum()), "costo_medio": float(cost.mean())}
