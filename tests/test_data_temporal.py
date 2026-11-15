import json

import pandas as pd
import pytest

from novamercado.data import load_data
from novamercado.evaluate import evaluate, temporal_masks


def write_data(path, history, stores, holidays, costs):
    history.to_csv(path / "historico_ventas.csv", index=False)
    stores.assign(nombre=["A", "B"], departamento=["G", "A"]).to_csv(path / "tiendas.csv", index=False)
    pd.DataFrame([{"familia_id": "pan", "nombre": "Pan"}]).to_csv(path / "familias.csv", index=False)
    holidays.assign(nombre=["Local", "Pago"]).to_csv(path / "feriados.csv", index=False)
    costs.to_csv(path / "costos.csv", index=False)


def test_split_disjoint_and_chronological(history):
    masks = temporal_masks(history.fecha, "2024-02-01", "2024-03-01", "2024-03-05")
    a, b, c = [history.loc[m, "fecha"] for m in masks.values()]
    assert a.max() < b.min() and b.max() < c.min()
    assert sum(m.astype(int) for m in masks.values()).eq(1).all()


@pytest.mark.parametrize("cal,test,end", [
    ("2024-03-01", "2024-02-01", "2024-03-05"),
    ("2024-02-01", "2024-03-01", "2027-01-01"),
])
def test_invalid_splits(history, cal, test, end):
    with pytest.raises(ValueError):
        temporal_masks(history.fecha, cal, test, end)


def test_loader_and_evaluation_end_to_end(tmp_path, history, stores, holidays, costs):
    write_data(tmp_path, history, stores, holidays, costs)
    original = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    data = load_data(tmp_path)
    assert len(data.hashes) == 5 and len(data.history) == 130
    result = evaluate(tmp_path, "2024-02-01", "2024-03-01", "2024-03-05")
    assert result["particiones"]["evaluacion"]["filas"] == 10
    assert set(result["modelos"]) == {"baseline_estacional", "hist_gradient_boosting"}
    assert result["modelos"]["hist_gradient_boosting"]["costo_total"] >= 0
    assert json.loads(json.dumps(result))["semilla"] == 42
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == original


@pytest.mark.parametrize("problem", ["duplicate", "negative", "unknown", "preopening"])
def test_invalid_training_data_rejected(tmp_path, history, stores, holidays, costs, problem):
    history = history.copy()
    if problem == "duplicate":
        history = pd.concat([history, history.iloc[:1]])
    elif problem == "negative":
        history.loc[0, "ventas"] = -1
    elif problem == "unknown":
        history.loc[0, "familia_id"] = "desconocida"
    else:
        history.loc[0, "fecha"] = pd.Timestamp("2023-12-31")
    write_data(tmp_path, history, stores, holidays, costs)
    with pytest.raises(ValueError):
        load_data(tmp_path)
