import numpy as np
import pandas as pd
import pytest
from threadpoolctl import threadpool_limits

from novamercado.costs import CostCalibrator, business_cost, metrics
from novamercado.features import build_features
from novamercado.models import SalesRegressor, SeasonalBaseline


def test_cost_formula_and_metrics(costs):
    np.testing.assert_array_equal(business_cost([10, 10], [8, 13], 2, 3), [4, 9])
    result = metrics([10, 10], [8, 13], [8, 13], ["pan", "pan"], costs)
    assert result["mae"] == 2.5
    assert result["rmse"] == np.sqrt(6.5)
    assert result["costo_total"] == 8


def test_more_expensive_shortage_increases_suggestion():
    actual = np.arange(21)
    predicted = np.full(21, 10)
    low = pd.DataFrame([{"familia_id": "a", "costo_faltante": 1., "costo_sobrante": 4.}])
    high = low.assign(costo_faltante=4., costo_sobrante=1.)
    families = ["a"] * 21
    a = CostCalibrator.fit(families, actual, predicted, low)
    b = CostCalibrator.fit(families, actual, predicted, high)
    assert a.suggest(["a"], [10]).item() == 4
    assert b.suggest(["a"], [10]).item() == 16
    # Óptimo empírico de costo asimétrico para esta distribución sintética.
    costs = [business_cost(actual, q, 4, 1).sum() for q in range(21)]
    assert b.suggest(["a"], [10]).item() == np.argmin(costs)


def test_suggestions_are_nonnegative_integers():
    c = CostCalibrator({"a": -2.})
    out = c.suggest(["a", "a"], [0., 1.5])
    assert np.issubdtype(out.dtype, np.integer)
    assert (out >= 0).all()
    with pytest.raises(ValueError):
        c.suggest(["a"], [np.nan])


def test_missing_family_calibration_rejected(costs):
    with pytest.raises(ValueError, match="Sin calibración"):
        CostCalibrator.fit(["otra"], [3], [2], pd.concat([
            costs, costs.assign(familia_id="otra")]))


@pytest.mark.parametrize("shortage,surplus", [(0, 1), (1, -1), (np.nan, 1)])
def test_invalid_cost_rates(shortage, surplus):
    with pytest.raises(ValueError, match="Costos"):
        business_cost([1], [1], shortage, surplus)


@pytest.mark.parametrize("actual,suggested", [([-1], [0]), ([1], [np.inf])])
def test_invalid_cost_inputs(actual, suggested):
    with pytest.raises(ValueError):
        business_cost(actual, suggested, 1, 1)


def test_models_train_and_predict_without_services(history, stores, holidays):
    x = build_features(history, history, stores, holidays)
    train = history.fecha < "2024-02-01"
    for model in [SeasonalBaseline(), SalesRegressor()]:
        with threadpool_limits(limits=2):
            model.fit(x.loc[train], history.loc[train, "ventas"].to_numpy())
            predicted = model.predict(x.loc[~train])
        assert len(predicted) == (~train).sum()
        assert np.isfinite(predicted).all() and (predicted >= 0).all()
    np.testing.assert_array_equal(SeasonalBaseline().predict(x), x.estacional)
