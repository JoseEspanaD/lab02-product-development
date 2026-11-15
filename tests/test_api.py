from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from novamercado.api import create_app
from novamercado.schemas import (ModelInfo, ObservationOutput, Prediction,
                                PredictionOutput, RunStatus)


class MemoryRepository:
    """Doble explícito: pruebas de contrato, no evidencia de persistencia SQL."""
    def __init__(self):
        self.requests = []
        self.observations = {}
        self.up = True

    def healthy(self):
        return self.up

    def rejected(self, endpoint, raw, detail, status=422, parsed=None, quality=None):
        self.requests.append((endpoint, status, detail))

    def save_prediction(self, raw, parsed, result):
        self.requests.append((parsed, result))

    def save_observation(self, raw, parsed, quality):
        count = 0
        for row in parsed.ventas:
            key = (parsed.fecha, parsed.tienda_id, row.familia_id)
            if self.observations.get(key) != row.ventas:
                self.observations[key] = row.ventas
                count += 1
        self.requests.append((parsed, quality))
        return count

    def observations_before(self, day):
        return pd.DataFrame([
            {"fecha": d, "tienda_id": s, "familia_id": f, "ventas": v, "en_promocion": None}
            for (d, s, f), v in self.observations.items() if d < day
        ], columns=["fecha", "tienda_id", "familia_id", "ventas", "en_promocion"])


class TestModel:
    __test__ = False

    def __init__(self):
        self.loaded = True
        self.history = None

    def info(self):
        return ModelInfo(nombre="doble_de_prueba", alias="test", version="test-1") if self.loaded else None

    def predict(self, request, history):
        self.history = history.copy()
        return self.info(), [Prediction(familia_id=f.familia_id, venta_esperada=10.5,
                                        cantidad_sugerida=11) for f in request.familias]


@pytest.fixture
def api_data(history, stores, holidays, costs):
    families = pd.DataFrame([{"familia_id": "pan", "nombre": "Pan"},
                             {"familia_id": "lacteos", "nombre": "Lácteos"}])
    h = pd.concat([history, history.assign(familia_id="lacteos")], ignore_index=True)
    return SimpleNamespace(history=h, stores=stores, holidays=holidays,
                           families=families, costs=costs, hashes={})


@pytest.fixture
def payload():
    return {"tienda_id": 1, "fecha": "2024-02-01", "familias": [
        {"familia_id": "pan", "en_promocion": 0},
        {"familia_id": "lacteos", "en_promocion": 2}]}


@pytest.fixture
def observations(payload):
    return {"tienda_id": payload["tienda_id"], "fecha": payload["fecha"], "ventas": [
        {"familia_id": f["familia_id"], "ventas": 12} for f in payload["familias"]]}


@pytest.fixture
def client(api_data):
    repository = MemoryRepository()
    model = TestModel()
    with TestClient(create_app(api_data, repository, model)) as client:
        yield client, repository, model


def test_valid_contract_repeated_prediction(client, payload):
    c, r, _ = client
    for _ in range(2):
        response = c.post("/v1/prediccion", json=payload)
        assert response.status_code == 200
        result = PredictionOutput.model_validate(response.json())
        assert result.version_modelo == "test-1"
        assert result.calidad.estado == "ok" and result.calidad.observaciones == []
        assert len(result.predicciones) == 2
    assert len(r.requests) == 2


@pytest.mark.parametrize("change", [
    {"tienda_id": "T01"}, {"tienda_id": "1"}, {"fecha": "01/02/2024"},
    {"fecha": "2024-02-01T00:00:00"},
])
def test_repair_general_fields(client, payload, change):
    payload.update(change)
    response = client[0].post("/v1/prediccion", json=payload)
    assert response.status_code == 200
    assert response.json()["calidad"]["estado"] == "corregido"


def test_repair_alias_family_promotions_and_dedup(client, payload):
    payload["tienda"] = payload.pop("tienda_id")
    payload["familias"][1] = {"familia_id": " LÁCTEOS ", "en_promocion": "2"}
    payload["familias"].append({"familia_id": "pan", "en_promocion": 0.0})
    response = client[0].post("/v1/prediccion", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["calidad"]["estado"] == "corregido"
    assert len(result["predicciones"]) == 2
    assert len(result["calidad"]["observaciones"]) >= 4


def test_warning_takes_precedence(client, payload):
    payload["tienda_id"] = "1"
    payload["extra"] = "ignorar"
    response = client[0].post("/v1/prediccion", json=payload)
    assert response.status_code == 200
    assert response.json()["calidad"]["estado"] == "advertencia"
    assert {n["accion"] for n in response.json()["calidad"]["observaciones"]} == {"reparar", "advertir"}


@pytest.mark.parametrize("case", ["missing", "conflict", "unknown_family", "negative_promo",
                                   "fractional_promo", "boolean_promo", "unknown_store",
                                   "boolean_store", "invalid_date", "before_opening", "alias_conflict", "huge_number"])
def test_rejections_are_explanatory_and_audited(client, payload, case):
    if case == "missing": payload["familias"].pop()
    elif case == "conflict": payload["familias"].append({"familia_id": "pan", "en_promocion": 5})
    elif case == "unknown_family": payload["familias"][0]["familia_id"] = "desconocida"
    elif case in ["negative_promo", "fractional_promo", "boolean_promo"]:
        payload["familias"][0]["en_promocion"] = {"negative_promo": -1, "fractional_promo": 2.5, "boolean_promo": True}[case]
    elif case == "unknown_store": payload["tienda_id"] = 999
    elif case == "boolean_store": payload["tienda_id"] = True
    elif case == "invalid_date": payload["fecha"] = "2024-02-30"
    elif case == "before_opening": payload["fecha"] = "2023-12-31"
    elif case == "huge_number": payload["familias"][0]["en_promocion"] = 10**20
    else: payload["tienda"] = 1
    response = client[0].post("/v1/prediccion", json=payload)
    assert response.status_code == 422 and response.json()["detail"]
    assert client[1].requests[-1][1] == 422


@pytest.mark.parametrize("raw", [b"", b"[]", b"null", b"{", b'{"x":NaN}', b'{"x":1,"x":2}'])
def test_invalid_json(client, raw):
    response = client[0].post("/v1/prediccion", content=raw)
    assert response.status_code == 422 and response.json()["detail"]


def test_idempotence_modified_count_and_partial_observations(client, observations):
    c = client[0]
    for expected in [2, 0]:
        response = c.post("/v1/observaciones", json=observations)
        assert response.status_code == 200
        assert ObservationOutput.model_validate(response.json()).registros_guardados == expected
    observations["ventas"][0]["ventas"] = 13
    assert c.post("/v1/observaciones", json=observations).json()["registros_guardados"] == 1
    observations["ventas"] = observations["ventas"][:1]
    assert c.post("/v1/observaciones", json=observations).json()["registros_guardados"] == 0


@pytest.mark.parametrize("value,status", [(-4, 422), ("1,292", 422), ("50,0", 200), ("812.5", 200)])
def test_sales_numeric_policy(client, observations, value, status):
    observations["ventas"][0]["ventas"] = value
    response = client[0].post("/v1/observaciones", json=observations)
    assert response.status_code == status


def test_no_future_sales_and_observation_precedence(client, payload, observations):
    c, _, m = client
    observations["fecha"] = "2024-01-31"
    observations["ventas"][0]["ventas"] = 999
    assert c.post("/v1/observaciones", json=observations).status_code == 200
    assert c.post("/v1/prediccion", json=payload).status_code == 200
    assert (m.history.fecha < pd.Timestamp(payload["fecha"])).all()
    assert m.history.loc[(m.history.fecha == "2024-01-31") & (m.history.familia_id == "pan") &
                         (m.history.tienda_id == 1), "ventas"].item() == 999


def test_admin_disconnected_and_health(client):
    c, repo, model = client
    assert c.post("/admin/reentrenar").status_code == 503
    assert c.get("/admin/reentrenar/desconocido").status_code == 404
    info = c.get("/modelo")
    assert info.status_code == 200 and set(info.json()) == {"nombre", "alias", "version"}
    health = c.get("/health")
    assert health.status_code == 200 and health.json()["estado"] == "degradado"
    assert "Airflow" in health.json()["motivo"]
    repo.up = False
    assert "PostgreSQL" in c.get("/health").json()["motivo"]
    model.loaded = False
    assert c.get("/health").status_code == 503
    assert c.get("/modelo").status_code == 503


def test_admin_adapter_contract(api_data):
    class Admin:
        def start(self): return "test-run"
        def status(self, id): return RunStatus(estado="exitoso", promovido=False, version="test-1", motivo="Prueba de contrato")
        def dependencies(self): return {"MLflow": True, "Airflow": True}
    with TestClient(create_app(api_data, MemoryRepository(), TestModel(), Admin())) as c:
        assert c.post("/admin/reentrenar").json() == {"id": "test-run"}
        assert c.post("/admin/reentrenar").status_code == 202
        assert c.get("/admin/reentrenar/test-run").json()["promovido"] is False
        assert c.get("/health").json() == {"estado": "ok"}
    with pytest.raises(ValidationError):
        RunStatus(estado="fallido")


def test_openapi_includes_canonical_inputs(client):
    schema = client[0].get("/openapi.json").json()
    body = schema["paths"]["/v1/prediccion"]["post"]["requestBody"]
    assert set(body["content"]["application/json"]["schema"]["required"]) == {"fecha", "tienda_id", "familias"}


@pytest.mark.parametrize("state", ["en_curso", "exitoso", "fallido"])
def test_all_administration_statuses(api_data, state):
    class Admin:
        def status(self, id):
            return RunStatus(estado=state) if state == "en_curso" else RunStatus(
                estado=state, promovido=False, version="test-1", motivo="Prueba explícita de adaptador")
    with TestClient(create_app(api_data, MemoryRepository(), TestModel(), Admin())) as c:
        response = c.get("/admin/reentrenar/test-run")
        assert response.status_code == 200
        assert response.json()["estado"] == state
        if state == "en_curso":
            assert response.json() == {"estado": "en_curso"}
        else:
            assert set(response.json()) == {"estado", "promovido", "version", "motivo"}
