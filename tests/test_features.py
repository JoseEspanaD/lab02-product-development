import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from novamercado.features import build_features


def test_current_and_future_sales_cannot_change_features(history, stores, holidays):
    requests = history[history.fecha == "2024-02-01"]
    expected = build_features(history, requests, stores, holidays)
    altered = history.copy()
    altered.loc[altered.fecha >= "2024-02-01", "ventas"] = 1e9
    requests = requests.assign(ventas=-999)
    assert_frame_equal(expected, build_features(altered, requests, stores, holidays))
    assert_frame_equal(expected, build_features(history[history.fecha < "2024-02-01"],
                                               requests, stores, holidays))


def test_batch_equals_day_by_day_observations(history, stores, holidays):
    requests = history[history.fecha.between("2024-02-01", "2024-02-04")]
    batch = build_features(history, requests, stores, holidays)
    sequential = pd.concat([
        build_features(history[history.fecha < date], rows, stores, holidays)
        for date, rows in requests.groupby("fecha", sort=False)
    ]).reset_index(drop=True)
    # Agrupación por día cambia orden; comparar claves y variables ordenadas.
    sort = ["tienda_id", "en_promocion", "dia_mes"]
    assert_frame_equal(batch.sort_values(sort).reset_index(drop=True),
                       sequential.sort_values(sort).reset_index(drop=True))


def test_calendar_lags_and_missing_day(history, stores, holidays):
    requests = history[(history.fecha == "2024-02-01") & (history.tienda_id == 1)]
    x = build_features(history, requests, stores, holidays)
    assert x.lag7.iloc[0] == 25
    assert x.media7.iloc[0] == np.mean(np.arange(25, 32))
    assert x.media28.iloc[0] == np.mean(np.arange(4, 32))
    assert x.estacional.iloc[0] == np.mean([25, 18, 11, 4])
    missing = history[history.fecha != "2024-01-25"]
    x = build_features(missing, requests, stores, holidays)
    assert x.dias_observados28.iloc[0] == 27
    # No confundir siete filas anteriores con siete días anteriores.
    assert x.lag7.iloc[0] == np.mean([18, 11, 4])


def test_local_and_national_events(history, stores, holidays):
    request = history[history.fecha.isin(pd.to_datetime(["2024-02-01", "2024-02-02"]))]
    x = build_features(history, request, stores, holidays)
    assert x.loc[(x.tienda_id == 1) & (x.dia_mes == 1), "feriado"].item() == 1
    assert x.loc[(x.tienda_id == 2) & (x.dia_mes == 1), "feriado"].item() == 0
    assert x.loc[x.dia_mes == 2, "pago"].eq(1).all()


def test_opening_is_not_imputed_as_observed_zero(history, stores, holidays):
    stores = stores.copy()
    stores["fecha_apertura"] = pd.Timestamp("2024-02-01")
    request = history[(history.fecha == "2024-02-01") & (history.tienda_id == 1)]
    x = build_features(history, request, stores, holidays)
    assert x.dias_observados28.item() == 0
    assert x.edad_tienda.item() == 0
    assert x.estacional.item() == 0
    with pytest.raises(ValueError, match="apertura"):
        build_features(history, request.assign(fecha=pd.Timestamp("2024-01-31")), stores, holidays)


def test_request_promotions_and_order_preserved(history, stores, holidays):
    requests = history[history.fecha == "2024-02-01"].iloc[::-1].copy()
    requests["en_promocion"] = [19, 0]
    x = build_features(history, requests, stores, holidays)
    assert x.tienda_id.tolist() == [2, 1]
    assert x.en_promocion.tolist() == [19, 0]


def test_duplicate_sales_rejected(history, stores, holidays):
    with pytest.raises(ValueError, match="duplicadas"):
        build_features(pd.concat([history, history.iloc[:1]]), history.iloc[:1], stores, holidays)
