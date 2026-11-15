"""Primera carga idempotente, bajo bloqueo PostgreSQL, sin entrenar en reinicios."""

import os
import tempfile

from .data import load_data
from .registry import Registry
from .repository import PostgresRepository
from .training import train_candidate


def bootstrap(data, repository, registry, validation_end, directory="/data"):
    with repository.model_lock():
        repository.initialize()
        if data is None:
            try:
                data = repository.load_data()
            except RuntimeError:
                data = load_data(directory)
        imported = repository.seed_data(data)
        current = registry.current()
        if current is not None:
            if current.tags.get("eligible") != "true":
                raise RuntimeError("Alias vigente no elegible; revisar Registry sin reentrenar bootstrap")
            return {"trained": False, "imported": imported, "version": str(current.version)}
        versions = registry.versions()
        if versions:
            # Recuperación de un fallo entre registro y movimiento del alias.
            eligible = [v for v in versions if v.tags.get("eligible") == "true"]
            if not eligible:
                raise RuntimeError("Existen versiones no elegibles; no reentrenar bootstrap automáticamente")
            version = max(eligible, key=lambda v: int(v.version))
            with tempfile.TemporaryDirectory() as directory:
                registry.load(version.version, directory)
            registry.promote(version.version)
            return {"trained": False, "imported": imported, "version": str(version.version)}
        artifact, report, example = train_candidate(data, validation_end)
        version = registry.register(artifact, report, example)
        with tempfile.TemporaryDirectory() as directory:
            registry.load(version.version, directory)
        if not report["eligible"]:
            raise RuntimeError(report["reason"])
        registry.promote(version.version)
        return {"trained": True, "imported": imported, "version": str(version.version), "report": report}


def main():
    import json
    repository = PostgresRepository(os.environ["DATABASE_URL"])
    registry = Registry(os.environ["MLFLOW_TRACKING_URI"],
                        os.environ.get("MODEL_NAME", "novamercado"), os.environ.get("MODEL_ALIAS", "champion"))
    result = bootstrap(None, repository, registry, os.environ.get("BOOTSTRAP_VALIDATION_END", "2025-11-16"),
                       os.environ.get("DATA_DIR", "/data"))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
