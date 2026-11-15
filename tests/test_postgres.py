"""Integración real, opcional: TEST_DATABASE_URL debe apuntar a una DB de pruebas."""

from concurrent.futures import ThreadPoolExecutor
import os
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest
from fastapi.testclient import TestClient

from novamercado.api import create_app
from novamercado.cleaning import Cleaner
from novamercado.repository import PostgresRepository
from novamercado.schemas import PredictionOutput
from test_api import api_data, payload, observations, TestModel


@pytest.fixture
def pg():
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL no configurada; requiere PostgreSQL real")
    schema = "test_" + uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    repository = PostgresRepository(dsn, schema)
    repository.initialize()
    # Esquemas únicos en DB descartable; no borrar recursos ajenos ni originales.
    return repository


def count(pg, table):
    with pg.connect() as c:
        return c.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(table))).fetchone()["n"]


def test_postgres_full_api_audit_repetitions(pg, api_data, payload, observations):
    with TestClient(create_app(api_data, pg, TestModel())) as c:
        payload["tienda_id"] = "T01"
        for _ in range(2):
            assert c.post("/v1/prediccion", json=payload).status_code == 200
        assert c.post("/v1/observaciones", json=observations).json()["registros_guardados"] == 2
        assert c.post("/v1/observaciones", json=observations).json()["registros_guardados"] == 0
        observations["ventas"][0]["ventas"] = 99
        assert c.post("/v1/observaciones", json=observations).json()["registros_guardados"] == 1
        assert c.post("/v1/prediccion", json={}).status_code == 422
    assert count(pg, "solicitudes") == 6
    assert count(pg, "predicciones") == 4
    assert count(pg, "observaciones") == 2
    with pg.connect() as conn:
        row = conn.execute("SELECT * FROM solicitudes WHERE status=200 ORDER BY id LIMIT 1").fetchone()
        assert row["calidad"]["estado"] == "corregido"
        assert row["calidad"]["observaciones"][0]["accion"] == "reparar"
        assert '"T01"' in row["cuerpo_original"]
        assert row["cuerpo_limpio"]["tienda_id"] == 1
        versions = conn.execute("SELECT DISTINCT version_modelo FROM predicciones").fetchall()
        assert versions == [{"version_modelo": "test-1"}]
    # Una instancia nueva conserva filas e inicializar esquema otra vez no borra nada.
    restarted = PostgresRepository(pg.dsn, pg.schema)
    restarted.initialize()
    assert count(restarted, "observaciones") == 2


def test_concurrent_identical_observations(pg, api_data, observations):
    parsed, quality = Cleaner(api_data).clean(observations, observation=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: pg.save_observation(b"{}", parsed, quality), range(8)))
    assert sorted(results) == [0] * 7 + [2]
    assert count(pg, "observaciones") == 2
    assert count(pg, "solicitudes") == 8


def test_prediction_transaction_rollback(pg, api_data, payload):
    parsed, quality = Cleaner(api_data).clean(payload)
    info, predictions = TestModel().predict(parsed, api_data.history)
    result = PredictionOutput(tienda_id=1, fecha=parsed.fecha, version_modelo=info.version,
                              predicciones=predictions + predictions[:1], calidad=quality)
    with pytest.raises(psycopg.errors.UniqueViolation):
        pg.save_prediction(b"{}", parsed, result)
    assert count(pg, "predicciones") == count(pg, "solicitudes") == 0


def test_promotion_history_latest_and_strict_cutoff(pg, api_data, payload, observations):
    with TestClient(create_app(api_data, pg, TestModel())) as c:
        assert c.post("/v1/prediccion", json=payload).status_code == 200
        payload["familias"][0]["en_promocion"] = 7
        assert c.post("/v1/prediccion", json=payload).status_code == 200
        assert c.post("/v1/observaciones", json=observations).status_code == 200
    from datetime import date
    assert pg.observations_before(date(2024, 2, 1)).empty
    rows = pg.observations_before(date(2024, 2, 2))
    assert rows.loc[rows.familia_id == "pan", "en_promocion"].item() == 7


def test_database_down_returns_503_without_credentials(api_data, payload):
    pg = PostgresRepository("host=127.0.0.1 port=1 dbname=not_real user=not_real password=private")
    with TestClient(create_app(api_data, pg, TestModel())) as c:
        response = c.post("/v1/prediccion", json=payload)
        assert response.status_code == 503
        assert "private" not in response.text


def test_unavailable_model_preserves_cleaning_audit(pg, api_data, payload):
    from novamercado.providers import Unavailable
    class UnavailableModel(TestModel):
        def predict(self, request, history):
            raise Unavailable("Modelo temporalmente no disponible")
    payload["tienda_id"] = "T01"
    with TestClient(create_app(api_data, pg, UnavailableModel())) as c:
        assert c.post("/v1/prediccion", json=payload).status_code == 503
    with pg.connect() as conn:
        row = conn.execute("SELECT status,cuerpo_limpio,calidad FROM solicitudes").fetchone()
    assert row["status"] == 503 and row["cuerpo_limpio"]["tienda_id"] == 1
    assert row["calidad"]["estado"] == "corregido"
    assert count(pg, "predicciones") == 0


def test_published_snapshot_is_idempotent_and_lock_is_exclusive(pg, api_data):
    api_data.hashes = {name: "synthetic-" + name for name in
                       ["tiendas.csv", "familias.csv", "feriados.csv", "costos.csv", "historico_ventas.csv"]}
    with pg.model_lock():
        assert pg.seed_data(api_data)
        other = PostgresRepository(pg.dsn, pg.schema)
        with pytest.raises(RuntimeError, match="en curso"):
            with other.model_lock(): pass
    assert not pg.seed_data(api_data)
    restored = pg.load_data()
    assert len(restored.history) == len(api_data.history)
    assert restored.hashes == api_data.hashes
    api_data.hashes["historico_ventas.csv"] = "modified"
    with pytest.raises(ValueError, match="distintos"):
        pg.seed_data(api_data)


def test_execution_result_immutable_and_submission_lock(pg):
    pg.save_execution('run', '1')
    pg.save_execution('run', '2')
    assert pg.execution('run')['version_inicial'] == '1'
    pg.record_incumbent('run', '2')
    assert pg.execution('run')['version_inicial'] == '2'
    result = {'estado': 'exitoso', 'promovido': True, 'version': '2', 'motivo': 'mejora'}
    pg.finish_execution('run', result)
    pg.finish_execution('run', {'estado': 'fallido'})
    assert pg.execution('run')['resultado'] == result
    pg.record_incumbent('run', '3')
    assert pg.execution('run')['version_inicial'] == '2'
    with pg.submission_lock():
        with pg.connect() as conn:
            assert conn.execute('SELECT pg_try_advisory_xact_lock(202602,4) AS locked').fetchone()['locked'] is False


@pytest.mark.parametrize('raw', [b'{"extra":"\\u0000"}', b'{"extra":"\\ud800"}', b'{"extra":"\x00"}'])
def test_invalid_unicode_is_rejected_and_audited(pg, api_data, raw):
    with TestClient(create_app(api_data, pg, TestModel())) as client:
        response = client.post('/v1/prediccion', content=raw,
                               headers={'Content-Type':'application/json'})
    assert response.status_code == 422, response.text
    assert response.json()['detail']
    with pg.connect() as conn:
        row = conn.execute('SELECT cuerpo_original,status FROM solicitudes').fetchone()
        assert row['status'] == 422
        assert '\x00' not in row['cuerpo_original']
