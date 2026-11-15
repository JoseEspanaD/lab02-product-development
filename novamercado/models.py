"""Baseline estacional y un único candidato de árboles, sin búsqueda de hiperparámetros."""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OrdinalEncoder

from .features import CATEGORICAL, NUMERIC


class SeasonalBaseline:
    """Media de hasta cuatro observaciones de igual día semanal; fallback media28."""

    def fit(self, x: pd.DataFrame, y: np.ndarray):
        return self

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        return np.maximum(0, x.estacional.to_numpy(dtype=float))


class SalesRegressor:
    def __init__(self):
        self.pipeline = make_pipeline(
            ColumnTransformer([
                ("categorias", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
                 CATEGORICAL),
                ("numericas", "passthrough", NUMERIC),
            ]),
            HistGradientBoostingRegressor(
                loss="squared_error", max_iter=150, max_leaf_nodes=31,
                learning_rate=0.08, l2_regularization=1.0,
                categorical_features=list(range(len(CATEGORICAL))),
                early_stopping=False, random_state=42,
            ),
        )

    def fit(self, x: pd.DataFrame, y: np.ndarray):
        self.pipeline.fit(x, y)
        return self

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        return np.maximum(0, self.pipeline.predict(x))
