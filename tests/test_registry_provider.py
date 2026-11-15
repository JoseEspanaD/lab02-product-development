from contextlib import nullcontext
from copy import deepcopy
from threading import Event, Thread
from time import monotonic
from types import SimpleNamespace

import pandas as pd
import pytest

from novamercado.bootstrap import bootstrap
from novamercado.data import Data
from novamercado.registered_provider import RegisteredModelProvider
from novamercado.registry import train_and_register
from novamercado.schemas import PredictionInput
from novamercado.training import promotion_decision, train_candidate
from novamercado.providers import Unavailable


@pytest.fixture
def trained(history, stores, holidays, costs):
    data = Data(history, stores, pd.DataFrame([{"familia_id": "pan", "nombre": "Pan"}]), holidays,
                costs, {"historico_ventas.csv": "synthetic"})
    artifact, report, example = train_candidate(data, "2024-03-05", calibration_days=7, validation_days=7)
    return data, artifact, report, example


class FakeRegistry:
    uri, name, alias = "http://registry-test", "novamercado", "champion"

    def __init__(self, artifact):
        self.artifact = artifact
        self.version = "1"
        self.up = True
        self.bad_download = False
        self.registered = []
        self.loads = 0

    def current(self):
        if not self.up:
            raise ConnectionError("Prueba explícita de caída")
        return SimpleNamespace(version=self.version, tags={"eligible": "true"}) if self.version else None

    def load(self, version, destination):
        self.loads += 1
        if self.bad_download:
            raise ValueError("Artefacto inválido de prueba")
        return self.artifact

    def versions(self): return self.registered

    def register(self, artifact, report, example):
        version = SimpleNamespace(version=str(len(self.registered) + 1), tags={"eligible": str(report["eligible"]).lower()})
        self.registered.append(version)
        self.artifact = artifact
        return version

    def promote(self, version): self.version = str(version)


def test_cache_outage_restart_alias_reload(trained, tmp_path):
    data, artifact, _, _ = trained
    registry = FakeRegistry(artifact)
    provider = RegisteredModelProvider(data, registry, tmp_path)
    assert provider.info() is None
    assert provider.refresh() and provider.info().version == "1"
    assert provider.healthy()
    loaded = registry.loads
    assert provider.refresh() and registry.loads == loaded
    registry.up = False
    assert not provider.refresh() and not provider.healthy()
    assert provider.info().version == "1"
    restarted = RegisteredModelProvider(data, registry, tmp_path)
    assert restarted.info().version == "1" and not restarted.healthy()
    request = PredictionInput(tienda_id=1, fecha="2024-03-06", familias=[{"familia_id": "pan", "en_promocion": 1}])
    info, result = restarted.predict(request, data.history)
    assert info.version == "1" and result[0].cantidad_sugerida >= 0
    registry.up, registry.version = True, "2"
    assert restarted.refresh() and restarted.info().version == "2"
    assert restarted.healthy()


def test_bad_candidate_keeps_memory_and_cache(trained, tmp_path):
    data, artifact, _, _ = trained
    registry = FakeRegistry(artifact)
    provider = RegisteredModelProvider(data, registry, tmp_path)
    assert provider.refresh()
    previous = provider.cache.read_bytes()
    registry.version, registry.bad_download = "2", True
    assert not provider.refresh()
    assert provider.info().version == "1" and provider.cache.read_bytes() == previous


def test_network_refresh_does_not_lock_inference(trained, tmp_path):
    data, artifact, _, _ = trained
    registry = FakeRegistry(artifact)
    provider = RegisteredModelProvider(data, registry, tmp_path)
    provider.refresh()
    entered, release = Event(), Event()
    def slow_load(version, destination):
        entered.set()
        assert release.wait(5)
        return artifact
    registry.version, registry.load = "2", slow_load
    thread = Thread(target=provider.refresh)
    thread.start()
    try:
        assert entered.wait(2)
        request = PredictionInput(tienda_id=1, fecha="2024-03-06", familias=[{"familia_id": "pan", "en_promocion": 0}])
        assert provider.predict(request, data.history)[0].version == "1"
    finally:
        release.set()
        thread.join(5)
    assert provider.info().version == "2"


def test_stale_health_and_temporal_guard(trained, tmp_path):
    data, artifact, _, _ = trained
    provider = RegisteredModelProvider(data, FakeRegistry(artifact), tmp_path)
    provider.refresh()
    provider._checked = monotonic() - 46
    assert not provider.healthy()
    request = PredictionInput(tienda_id=1, fecha="2024-03-05", familias=[{"familia_id": "pan", "en_promocion": 0}])
    with pytest.raises(Unavailable, match="corte temporal"):
        provider.predict(request, data.history)


def test_other_registry_or_data_cannot_use_cache(trained, tmp_path):
    data, artifact, _, _ = trained
    registry = FakeRegistry(artifact)
    RegisteredModelProvider(data, registry, tmp_path).refresh()
    registry.alias = "otro"
    assert RegisteredModelProvider(data, registry, tmp_path).info() is None
    registry.alias = "champion"
    changed = deepcopy(data)
    changed.hashes = {"historico_ventas.csv": "changed"}
    assert RegisteredModelProvider(changed, registry, tmp_path).info() is None


@pytest.mark.parametrize("new,old,baseline,expected", [(4, 5, 6, True), (5, 5, 6, False),
                                                     (6, 5, 7, False), (4, 5, 4, False),
                                                     (float("nan"), 5, 6, False)])
def test_strict_cost_promotion(new, old, baseline, expected):
    def result(cost): return {"mae": 1, "rmse": 2, "costo_total": cost, "costo_medio": cost}
    assert promotion_decision(result(new), result(baseline), result(old))[0] is expected


class FakeRepository:
    def __init__(self): self.seeded = False
    def initialize(self): pass
    def model_lock(self): return nullcontext()
    def seed_data(self, data):
        imported = not self.seeded
        self.seeded = True
        return imported


def test_bootstrap_existing_alias_never_trains(trained, monkeypatch):
    data, artifact, _, _ = trained
    def forbidden(*a, **kw): raise AssertionError("No volver a entrenar")
    monkeypatch.setattr("novamercado.bootstrap.train_candidate", forbidden)
    repo = FakeRepository()
    registry = FakeRegistry(artifact)
    assert bootstrap(data, repo, registry, "2024-03-05")["trained"] is False
    assert bootstrap(data, repo, registry, "2024-03-05")["imported"] is False


def test_bootstrap_recovers_registered_version_without_fit(trained, monkeypatch):
    data, artifact, _, _ = trained
    def forbidden(*a, **kw): raise AssertionError("No volver a entrenar")
    monkeypatch.setattr("novamercado.bootstrap.train_candidate", forbidden)
    registry = FakeRegistry(artifact)
    registry.version = None
    registry.registered = [SimpleNamespace(version="1", tags={"eligible": "true"})]
    assert bootstrap(data, FakeRepository(), registry, "2024-03-05")["version"] == "1"
    assert registry.version == "1"


def test_failed_fit_never_changes_alias(trained, monkeypatch):
    data, artifact, _, _ = trained
    def fail(*a, **kw): raise RuntimeError("Fallo de entrenamiento controlado")
    monkeypatch.setattr("novamercado.registry.train_candidate", fail)
    registry = FakeRegistry(artifact)
    with pytest.raises(RuntimeError):
        train_and_register(data, FakeRepository(), registry, "2024-03-05")
    assert registry.version == "1"


def test_rejected_candidate_is_registered_but_not_promoted(trained, monkeypatch):
    data, artifact, report, example = trained
    report = {**report, "eligible": False, "reason": "No mejora el costo"}
    monkeypatch.setattr("novamercado.registry.train_candidate", lambda *a, **kw: (artifact, report, example))
    registry = FakeRegistry(artifact)
    registry.registered = [SimpleNamespace(version="1", tags={"eligible": "true"})]
    result = train_and_register(data, FakeRepository(), registry, "2024-03-05")
    assert not result["promovido"] and registry.version == "1"
    assert result["candidate_version"] == "2"


def test_insufficient_new_validation_rejected(trained):
    data, artifact, _, _ = trained
    with pytest.raises(ValueError, match="posterior"):
        train_candidate(data, "2024-03-05", artifact, calibration_days=7, validation_days=7)


def test_validation_labels_never_fit_model_or_calibrator(trained):
    data, artifact, report, example = trained
    changed = deepcopy(data)
    start = pd.Timestamp(report["splits"]["validation"]["start"])
    changed.history.loc[changed.history.fecha >= start, "ventas"] = 1e6
    other, _, _ = train_candidate(changed, "2024-03-05", calibration_days=7, validation_days=7)
    pd.testing.assert_frame_equal(artifact.predict(example), other.predict(example))


def test_cache_write_failure_keeps_loaded_model(trained, tmp_path, monkeypatch):
    data, artifact, _, _ = trained
    registry = FakeRegistry(artifact)
    provider = RegisteredModelProvider(data, registry, tmp_path)
    provider.refresh()
    previous = provider.cache.read_bytes()
    registry.version = "2"
    def fail(*a, **kw): raise OSError("Disco no disponible en prueba")
    monkeypatch.setattr("novamercado.registered_provider.joblib.dump", fail)
    assert not provider.refresh()
    assert provider.info().version == "1" and provider.cache.read_bytes() == previous


def test_promotion_failure_keeps_alias(trained, monkeypatch):
    data, artifact, report, example = trained
    report = {**report, "eligible": True}
    monkeypatch.setattr("novamercado.registry.train_candidate", lambda *a, **kw: (artifact, report, example))
    registry = FakeRegistry(artifact)
    registry.registered = [SimpleNamespace(version="1", tags={"eligible": "true"})]
    def fail(version): raise ConnectionError("Promoción fallida en prueba")
    registry.promote = fail
    with pytest.raises(ConnectionError):
        train_and_register(data, FakeRepository(), registry, "2024-03-05")
    assert registry.version == "1"


def test_bootstrap_trains_once(trained, monkeypatch):
    data, artifact, report, example = trained
    calls = []
    def fit(*args):
        calls.append(True)
        return artifact, {**report, "eligible": True}, example
    monkeypatch.setattr("novamercado.bootstrap.train_candidate", fit)
    registry, repo = FakeRegistry(artifact), FakeRepository()
    registry.version = None
    assert bootstrap(data, repo, registry, "2024-03-05")["trained"]
    assert not bootstrap(data, repo, registry, "2024-03-05")["trained"]
    assert len(calls) == 1


def test_corrupt_cache_recovers_from_registry(trained, tmp_path):
    data, artifact, _, _ = trained
    (tmp_path / "current.joblib").write_bytes(b"cache invalida de prueba")
    provider = RegisteredModelProvider(data, FakeRegistry(artifact), tmp_path)
    assert provider.info() is None
    assert provider.refresh() and provider.info().version == "1"


def test_ineligible_alias_cannot_replace_model(trained, tmp_path):
    data, artifact, _, _ = trained
    registry = FakeRegistry(artifact)
    provider = RegisteredModelProvider(data, registry, tmp_path)
    provider.refresh()
    registry.current = lambda: SimpleNamespace(version="2", tags={"eligible": "false"})
    assert not provider.refresh() and provider.info().version == "1"


def test_bootstrap_ineligible_alias_never_retrains(trained):
    data, artifact, _, _ = trained
    registry = FakeRegistry(artifact)
    registry.current = lambda: SimpleNamespace(version="1", tags={"eligible": "false"})
    with pytest.raises(RuntimeError, match="no elegible"):
        bootstrap(data, FakeRepository(), registry, "2024-03-05")


@pytest.mark.filterwarnings("ignore:.*Any type hint is inferred as AnyType.*:UserWarning")
@pytest.mark.filterwarnings("ignore:codecs.open.*is deprecated.*:DeprecationWarning")
def test_mlflow_serialization_round_trip_without_server(trained, tmp_path):
    # Dos avisos internos conocidos de MLflow 3.17/Python 3.14; sin filtrar código propio.
    import mlflow.sklearn
    data, artifact, _, example = trained
    path = tmp_path / "model"
    mlflow.sklearn.save_model(artifact, str(path), serialization_format="cloudpickle",
                              pip_requirements=["mlflow-skinny==3.17.2", "scikit-learn==1.9.1"])
    restored = mlflow.sklearn.load_model(str(path))
    restored.validate()
    pd.testing.assert_frame_equal(artifact.predict(example), restored.predict(example))


def test_restart_uses_snapshot_without_original_files(trained, monkeypatch):
    data, artifact, _, _ = trained
    repo = FakeRepository()
    repo.seeded = True
    repo.load_data = lambda: data
    def forbidden(*a, **kw): raise AssertionError("No releer originales en reinicio")
    monkeypatch.setattr("novamercado.bootstrap.load_data", forbidden)
    result = bootstrap(None, repo, FakeRegistry(artifact), "2024-03-05")
    assert not result["trained"] and not result["imported"]


def test_empty_snapshot_loads_originals_once(trained, monkeypatch):
    data, artifact, report, example = trained
    repo, registry, reads = FakeRepository(), FakeRegistry(artifact), []
    registry.version = None
    def empty(): raise RuntimeError("No hay snapshot todavía")
    repo.load_data = empty
    def read(directory):
        reads.append(directory)
        return data
    monkeypatch.setattr("novamercado.bootstrap.load_data", read)
    monkeypatch.setattr("novamercado.bootstrap.train_candidate",
                        lambda *a: (artifact, {**report, "eligible": True}, example))
    result = bootstrap(None, repo, registry, "2024-03-05", directory="published")
    assert result["trained"] and result["imported"] and reads == ["published"]
