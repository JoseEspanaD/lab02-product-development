"""Integración con reinicios de contenedores de prueba; conserva sus volúmenes.

Usar un COMPOSE_PROJECT_NAME nuevo y puertos libres en el archivo de entorno.
Requiere imagen ya construida, Docker, los datos docentes y .venv activa.
"""

import argparse
import json
from pathlib import Path
import subprocess
import time

import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--mlflow-url", default="http://127.0.0.1:5000")
    parser.add_argument("--output", default="outputs/fase3_integracion.json")
    parser.add_argument("--resume-after-promotion", action="store_true")
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    compose = ["docker", "compose", "--env-file", args.env_file]
    log = output.with_suffix(".log")

    def command(*arguments):
        result = subprocess.run(compose + list(arguments), capture_output=True, text=True, timeout=580)
        with log.open("a") as stream:
            stream.write(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"Falló compose {arguments[0]}; revisar {log}")
        return result.stdout

    def get(path):
        try:
            response = requests.get(args.api_url + path, timeout=3)
            return response.status_code, response.json()
        except (requests.RequestException, ValueError):
            return None, {}

    def post(path, payload):
        response = requests.post(args.api_url + path, json=payload, timeout=15)
        assert response.status_code == 200, (path, response.status_code, response.text[:200])
        return response.json()

    def wait(predicate, seconds):
        start = time.monotonic()
        while time.monotonic() - start < seconds:
            if predicate():
                return time.monotonic() - start
            time.sleep(0.5)
        raise AssertionError(f"Condición no alcanzada en {seconds} s")

    def mlflow_ready():
        status, health = get("/health")
        return status == 200 and (health.get("estado") == "ok" or health.get("motivo") == "No disponible: Airflow")

    from novamercado.registry import Registry
    registry = Registry(args.mlflow_url)
    report = json.loads(output.read_text()) if args.resume_after_promotion else {}
    code = (
        "import os,json; from novamercado.repository import PostgresRepository; "
        "from novamercado.registry import Registry,train_and_register; "
        "p=PostgresRepository(os.environ['DATABASE_URL']); "
        "r=Registry(os.environ['MLFLOW_TRACKING_URI']); "
        "print(json.dumps(train_and_register(p.load_data(),p,r,'2026-02-28')))"
    )
    if not args.resume_after_promotion:
        started = time.monotonic()
        command("up", "-d", "--no-build")
        wait(mlflow_ready, 500)
        report["cold_start_seconds"] = time.monotonic() - started
        assert report["cold_start_seconds"] < 600
        print("Arranque desde cero listo", flush=True)

        current = registry.current()
        assert current is not None and current.version == "1", "Usar un proyecto Compose nuevo para esta prueba"
        report["initial_version"] = current.version
        experiment = registry.client.get_experiment_by_name("novamercado-ventas")
        runs = registry.client.search_runs([experiment.experiment_id])
        assert len(runs) == 1 and runs[0].info.status == "FINISHED"
        assert len(runs[0].inputs.dataset_inputs) == 5
        report["bootstrap_metrics"] = runs[0].data.metrics
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        payload = json.loads(Path("data/ejemplos/prediccion_valida.json").read_text())
        assert post("/v1/prediccion", payload)["version_modelo"] == "1"
        payload["fecha"] = "2026-03-02"
        observation = json.loads(Path("data/ejemplos/observacion_valida.json").read_text())
        observation["fecha"] = "2026-03-01"
        assert post("/v1/observaciones", observation)["registros_guardados"] == 12
        assert post("/v1/observaciones", observation)["registros_guardados"] == 0
        assert post("/v1/prediccion", payload)["version_modelo"] == "1"

        # Mismo punto de entrada que podrá importar un futuro DAG, sin crear DAG ahora.
        trained_start = time.monotonic()
        text = command("exec", "-T", "api", "python", "-c", code)
        result = json.loads(next(line for line in reversed(text.splitlines()) if line.startswith("{")))
        assert result["promovido"] and result["version"] == "2", result["motivo"]
        report["candidate_seconds"] = time.monotonic() - trained_start
        assert report["candidate_seconds"] < 600
        report["promotion_metrics"] = result["report"]["metrics"]
        report["reload_seconds_upper_bound"] = report["candidate_seconds"] + wait(
            lambda: get("/modelo")[1].get("version") == "2", 120)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        assert post("/v1/prediccion", payload)["version_modelo"] == "2"
        print("Promoción real y recarga sin reinicio verificadas", flush=True)

    else:
        wait(mlflow_ready, 120)
        assert registry.current().version == "2"
    experiment = registry.client.get_experiment_by_name("novamercado-ventas")
    payload = json.loads(Path("data/ejemplos/prediccion_valida.json").read_text())
    payload["fecha"] = "2026-03-02"

    # Una versión no elegible tampoco se carga si alguien mueve manualmente el alias.
    version = registry.client.get_model_version(registry.name, "2")
    import mlflow
    mlflow.set_tracking_uri(registry.uri)
    mlflow.set_registry_uri(registry.uri)
    rejected = [v for v in registry.versions() if v.tags.get("eligible") == "false"]
    bad = rejected[0] if rejected else mlflow.register_model(version.source, registry.name, tags={"eligible": "false"})
    registry.client.set_registered_model_alias(registry.name, registry.alias, bad.version)
    try:
        wait(lambda: "MLflow" in get("/health")[1].get("motivo", ""), 60)
        assert get("/modelo")[1]["version"] == "2"
        assert post("/v1/prediccion", payload)["version_modelo"] == "2"
    finally:
        registry.client.set_registered_model_alias(registry.name, registry.alias, "2")
    wait(mlflow_ready, 120)
    report["ineligible_alias_keeps_model"] = True

    # Mismo bloque de validación: no hay ventana nueva; el trabajo falla sin promoción.
    failed = subprocess.run(compose + ["exec", "-T", "api", "python", "-c", code],
                            capture_output=True, text=True, timeout=120)
    assert failed.returncode != 0
    assert registry.current().version == "2"
    report["failed_training_keeps_alias"] = True

    before = post("/v1/prediccion", payload)
    stopped_at = time.monotonic()
    command("stop", "mlflow")
    try:
        report["degraded_seconds"] = time.monotonic() - stopped_at + wait(
            lambda: "MLflow" in get("/health")[1].get("motivo", ""), 55)
        assert report["degraded_seconds"] < 60
        during = post("/v1/prediccion", payload)
        assert during["predicciones"] == before["predicciones"]
        command("restart", "api")
        wait(lambda: get("/modelo")[0] == 200, 90)
        offline = post("/v1/prediccion", payload)
        assert offline["version_modelo"] == "2" and offline["predicciones"] == before["predicciones"]
        report["offline_api_restart_uses_cache"] = True
    finally:
        recovery_start = time.monotonic()
        command("start", "mlflow")
    report["recovery_seconds"] = time.monotonic() - recovery_start + wait(mlflow_ready, 110)
    assert report["recovery_seconds"] < 120
    print("Caída de MLflow, inferencia y reinicio offline verificados", flush=True)

    def snapshot():
        code = (
            "import os,json; from novamercado.repository import PostgresRepository; "
            "p=PostgresRepository(os.environ['DATABASE_URL']); "
            "c=p.connect(); print(json.dumps({t:c.execute('SELECT count(*) AS n FROM '+t).fetchone()['n'] "
            "for t in ['solicitudes','predicciones','observaciones','historico','datos_publicados']})); c.close()"
        )
        return json.loads(command("exec", "-T", "api", "python", "-c", code).strip())

    counts = snapshot()
    run_count = len(registry.client.search_runs([experiment.experiment_id]))
    version_count = len(registry.versions())
    command("down")  # Conserva TODOS los volúmenes; nunca pasar -v.
    warm = time.monotonic()
    command("up", "-d", "--no-build")
    wait(mlflow_ready, 500)
    report["warm_start_seconds"] = time.monotonic() - warm
    assert snapshot() == counts
    assert len(registry.client.search_runs([experiment.experiment_id])) == run_count
    assert len(registry.versions()) == version_count
    assert registry.current().version == get("/modelo")[1]["version"] == "2"
    logs = command("logs", "--no-log-prefix", "bootstrap")
    boot = json.loads(next(line for line in reversed(logs.splitlines()) if line.startswith("{")))
    assert not boot["trained"] and not boot["imported"]
    report.update({"counts_after_restart": counts, "bootstrap_second_start": boot,
                   "run_count": run_count, "version_count": version_count,
                   "final_alias_version": "2", "health": get("/health")[1]})
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
