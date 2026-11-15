"""Caché persistente y refresco de Registry sin red en el camino de inferencia."""

from contextlib import suppress
import os
from pathlib import Path
import tempfile
from threading import Event, Lock, Thread
from time import monotonic

import joblib
import pandas as pd
from threadpoolctl import threadpool_limits

from .features import build_features
from .providers import DisconnectedAdministration, Unavailable
from .schemas import ModelInfo, Prediction
from .training import ForecastArtifact


class RegisteredModelProvider:
    def __init__(self, data, registry, cache_dir, interval=10):
        self.data, self.registry = data, registry
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache = self.cache_dir / "current.joblib"
        self.interval = interval
        self._lock = Lock()
        self._refresh_lock = Lock()
        self._stop = Event()
        self._thread = None
        self._state = None
        self._available = False
        self._checked = 0.0
        if self.cache.exists():
            with suppress(Exception):
                state = joblib.load(self.cache)
                if state["identity"] == self.identity:
                    state["artifact"].validate()
                    self._state = state

    @property
    def identity(self):
        return (self.registry.uri, self.registry.name, self.registry.alias, tuple(sorted(self.data.hashes.items())))

    def info(self):
        with self._lock:
            return self._state["info"] if self._state else None

    def healthy(self):
        with self._lock:
            return self._available and monotonic() - self._checked < 45

    def refresh(self):
        with self._refresh_lock:
            try:
                version = self.registry.current()
                if version is None:
                    raise Unavailable("Alias no disponible")
                if version.tags.get("eligible") != "true":
                    raise Unavailable("Alias apunta a una versión no elegible")
                current = self.info()
                if current is None or current.version != str(version.version):
                    with tempfile.TemporaryDirectory(dir=self.cache_dir) as directory:
                        artifact = self.registry.load(version.version, directory)
                        if (artifact.dataset_hashes != self.data.hashes or
                                set(artifact.calibrator.adjustments) != set(self.data.families.familia_id)):
                            raise ValueError("Modelo incompatible con los catálogos o datos publicados")
                    state = {"identity": self.identity, "artifact": artifact,
                             "info": ModelInfo(nombre=self.registry.name, alias=self.registry.alias,
                                               version=str(version.version))}
                    temporary = self.cache.with_suffix(".tmp")
                    try:
                        joblib.dump(state, temporary)
                        os.replace(temporary, self.cache)
                    finally:
                        temporary.unlink(missing_ok=True)
                    with self._lock:
                        self._state = state
                with self._lock:
                    self._available, self._checked = True, monotonic()
                return True
            except Exception:
                # Mantener modelo y caché anteriores. No exponer URLs/credenciales.
                with self._lock:
                    self._available, self._checked = False, monotonic()
                return False

    def start(self):
        def loop():
            while not self._stop.is_set():
                self.refresh()
                self._stop.wait(self.interval)
        self._thread = Thread(target=loop, name="registry-refresh", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    def predict(self, request, history):
        with self._lock:
            state = self._state
        if state is None:
            raise Unavailable("No hay modelo cargado")
        artifact = state["artifact"]
        if pd.Timestamp(request.fecha) < pd.Timestamp(artifact.available_from):
            raise Unavailable("Modelo no aplicable: fecha anterior a su corte temporal de selección")
        rows = pd.DataFrame([{"fecha": request.fecha, "tienda_id": request.tienda_id,
                              "familia_id": f.familia_id, "en_promocion": f.en_promocion}
                             for f in request.familias])
        x = build_features(history, rows, self.data.stores, self.data.holidays)
        with threadpool_limits(limits=2):
            output = artifact.predict(x)
        return state["info"], [Prediction(familia_id=f, venta_esperada=float(y), cantidad_sugerida=int(q))
                               for f, y, q in zip(rows.familia_id, output.venta_esperada, output.cantidad_sugerida)]


class RegistryAdministration(DisconnectedAdministration):
    def __init__(self, provider):
        self.provider = provider

    def dependencies(self):
        return {"MLflow": self.provider.healthy(), "Airflow": False}
