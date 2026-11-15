"""Tracking y Registry reales; champion se modifica solo al terminar la validación."""

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "5")
os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
os.environ.setdefault("MLFLOW_ARTIFACT_UPLOAD_DOWNLOAD_TIMEOUT", "10")
os.environ.setdefault("MLFLOW_ENABLE_ARTIFACTS_PROGRESS_BAR", "false")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
# El Registry configurado es el del propio producto; sus modelos incluyen Python.
os.environ.setdefault("MLFLOW_ALLOW_PICKLE_DESERIALIZATION", "true")

import mlflow
import mlflow.sklearn
from mlflow import MlflowClient
from mlflow.entities import Dataset, DatasetInput, InputTag
from mlflow.exceptions import MlflowException
from mlflow.models import infer_signature

from .training import ForecastArtifact, train_candidate


class Registry:
    def __init__(self, uri, name="novamercado", alias="champion"):
        self.uri, self.name, self.alias = uri, name, alias
        self.client = MlflowClient(tracking_uri=uri, registry_uri=uri)

    def current(self):
        try:
            return self.client.get_model_version_by_alias(self.name, self.alias)
        except MlflowException as exc:
            if exc.error_code == "RESOURCE_DOES_NOT_EXIST":
                return None
            raise

    def versions(self):
        return self.client.search_model_versions(f"name='{self.name}'")

    def load(self, version, destination):
        mlflow.set_tracking_uri(self.uri)
        mlflow.set_registry_uri(self.uri)
        Path(destination).mkdir(parents=True, exist_ok=True)
        artifact = mlflow.sklearn.load_model(f"models:/{self.name}/{version}", dst_path=str(destination))
        if not isinstance(artifact, ForecastArtifact):
            raise ValueError("Artefacto incompatible con la API")
        artifact.validate()
        return artifact

    def register(self, artifact, report, example):
        mlflow.set_tracking_uri(self.uri)
        mlflow.set_registry_uri(self.uri)
        mlflow.set_experiment("novamercado-ventas")
        with mlflow.start_run(run_name="entrenamiento-temporal") as run:
            params = {"algorithm": "HistGradientBoostingRegressor", "seed": 42,
                      "max_iter": 150, "max_leaf_nodes": 31, "learning_rate": 0.08,
                      "l2_regularization": 1, "implementation": "fase3-v1",
                      "source_revision": os.environ.get("SOURCE_REVISION", "no-proporcionada"),
                      "requirements_sha256": hashlib.sha256(Path("requirements.txt").read_bytes()).hexdigest()}
            for name, split in report["splits"].items():
                params.update({f"{name}_{key}": value for key, value in split.items()})
            params.update({f"sha256_{key}": value for key, value in report["hashes"].items()})
            mlflow.log_params(params)
            for name, result in report["metrics"].items():
                mlflow.log_metrics({f"{name}_{key}": value for key, value in result.items()})
            mlflow.log_metric("training_total_seconds", report["seconds"])
            mlflow.set_tags({"promotion_eligible": str(report["eligible"]).lower(),
                             "promotion_reason": report["reason"]})
            mlflow.log_dict(report, "validacion.json")
            # Linaje de datos: metadatos y hashes; nunca subir filas originales.
            inputs = [DatasetInput(Dataset(name=filename, digest=digest[:36],
                                             source_type="local", source=json.dumps({"file": filename, "sha256": digest})),
                                    tags=[InputTag("mlflow.data.context", "training-validation")])
                      for filename, digest in report["hashes"].items()]
            self.client.log_inputs(run.info.run_id, inputs)
            requirements = [f"{p}=={importlib.metadata.version(p)}"
                            for p in ["mlflow-skinny", "cloudpickle", "numpy", "pandas", "scikit-learn", "joblib", "pydantic"]]
            logged = mlflow.sklearn.log_model(
                artifact, name="pronostico", code_paths=["novamercado"],
                serialization_format="cloudpickle",
                pip_requirements=requirements,
                signature=infer_signature(example, artifact.predict(example)),
            )
            version = mlflow.register_model(logged.model_uri, self.name,
                tags={"eligible": str(report["eligible"]).lower(),
                      "available_from": artifact.available_from,
                      "validation_end": report["splits"]["validation"]["end"]})
        return version

    def promote(self, version):
        candidate = self.client.get_model_version(self.name, str(version))
        if candidate.tags.get("eligible") != "true":
            raise ValueError("Versión no elegible para promoción")
        # Única mutación final; no escribir nada más que pueda fallar después.
        self.client.set_registered_model_alias(self.name, self.alias, str(version))


def train_and_register(data, repository, registry, validation_end):
    """Punto de entrada para trabajos futuros; no dispara ni implementa un DAG."""
    import tempfile
    with repository.model_lock():
        current = registry.current()
        with tempfile.TemporaryDirectory() as directory:
            incumbent = registry.load(current.version, directory) if current else None
            artifact, report, example = train_candidate(data, validation_end, incumbent)
            version = registry.register(artifact, report, example)
            # Validar también el artefacto descargado ANTES de mover el alias.
            registry.load(version.version, directory)
            if report["eligible"]:
                registry.promote(version.version)
            return {"promovido": report["eligible"],
                    "version": str(version.version if report["eligible"] else current.version if current else ""),
                    "motivo": report["reason"], "candidate_version": str(version.version), "report": report}
