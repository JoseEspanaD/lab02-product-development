import pandas as pd
import pytest


@pytest.fixture
def stores():
    return pd.DataFrame([
        {"tienda_id": 1, "ciudad": "Guatemala", "tipo": "express",
         "fecha_apertura": pd.Timestamp("2024-01-01")},
        {"tienda_id": 2, "ciudad": "Cobán", "tipo": "supermercado",
         "fecha_apertura": pd.Timestamp("2024-01-01")},
    ])


@pytest.fixture
def holidays():
    return pd.DataFrame([
        {"fecha": pd.Timestamp("2024-02-01"), "tipo": "feriado", "ambito": "Guatemala"},
        {"fecha": pd.Timestamp("2024-02-02"), "tipo": "pago", "ambito": "nacional"},
    ])


@pytest.fixture
def history():
    return pd.DataFrame([
        {"fecha": date, "tienda_id": store, "familia_id": "pan",
         "ventas": float(i + 1), "en_promocion": i % 3}
        for store in [1, 2]
        for i, date in enumerate(pd.date_range("2024-01-01", periods=65))
    ])


@pytest.fixture
def costs():
    return pd.DataFrame([{"familia_id": "pan", "costo_faltante": 1., "costo_sobrante": 2.}])
