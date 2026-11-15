import pandas as pd
import pytest

from novamercado.costs import CostCalibrator
from novamercado.data import Data
from novamercado.models import SalesRegressor
from novamercado.providers import LocalModelProvider, Unavailable
from novamercado.schemas import PredictionInput


def test_real_local_model_is_cut_before_prediction(stores, holidays, costs):
    h = pd.DataFrame([{"fecha": d, "tienda_id": 1, "familia_id": "pan",
                       "ventas": 10 + i % 7, "en_promocion": i % 2}
                      for i, d in enumerate(pd.date_range("2024-01-01", periods=180))])
    data = Data(h, stores, pd.DataFrame([{"familia_id": "pan", "nombre": "Pan"}]),
                holidays, costs, {"historico_ventas.csv": "synthetic"})
    provider = LocalModelProvider(data)
    request = PredictionInput(tienda_id=1, fecha="2024-05-01",
                               familias=[{"familia_id": "pan", "en_promocion": 1}])
    info, predictions = provider.predict(request, h)
    assert provider.cutoff == pd.Timestamp(request.fecha)
    assert isinstance(provider.bundle.model, SalesRegressor)
    assert isinstance(provider.bundle.calibrator, CostCalibrator)
    assert len(predictions) == 1 and predictions[0].cantidad_sugerida >= 0
    assert info.alias == "local" and info.version.startswith("local-2024-05-01")
    # Mutar ventas actuales/futuras no cambia ajuste ni calibración del corte anterior.
    data.history = h.copy()
    data.history.loc[data.history.fecha >= "2024-05-01", "ventas"] = 1e6
    other = LocalModelProvider(data)
    _, changed = other.predict(request, data.history)
    assert changed == predictions


def test_insufficient_history_never_reports_loaded(stores, holidays, costs, history):
    data = Data(history, stores, pd.DataFrame([{"familia_id": "pan"}]), holidays, costs,
                {"historico_ventas.csv": "test"})
    provider = LocalModelProvider(data)
    with pytest.raises(Unavailable):
        provider.prepare("2024-01-02")
    assert provider.info() is None
