"""Integración destructiva solo para servicios del proyecto de prueba; no borra volúmenes."""
import argparse
import json
from pathlib import Path
import subprocess
import time

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--api-url', default='http://127.0.0.1:18004')
    parser.add_argument('--output', default='outputs/fase4_integracion.json')
    args = parser.parse_args()
    compose = ['docker', 'compose', '--env-file', args.env_file]
    result = {}

    def docker(*cmd):
        try:
            return subprocess.check_output(compose + list(cmd), text=True, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as exc:
            Path('outputs/fase4-compose-error.log').write_text(exc.output)
            raise

    def api(path, body=None):
        if body is None:
            return requests.get(args.api_url+path, timeout=15)
        if path == '/admin/reentrenar':
            return requests.post(args.api_url+path, timeout=15)
        return requests.post(args.api_url+path, json=body, timeout=15)

    def wait_for(predicate, limit=120):
        start = time.monotonic()
        while time.monotonic()-start < limit:
            try:
                if predicate():
                    elapsed = time.monotonic()-start
                    assert elapsed < limit
                    return elapsed
            except (requests.RequestException, AssertionError):
                pass
            time.sleep(2)
        raise AssertionError('Tiempo agotado')

    def save():
        Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')

    start = time.monotonic()
    docker('up', '-d', '--no-build')
    wait_for(lambda: api('/health').json().get('estado') == 'ok', 600)
    result['initial_start_seconds'] = time.monotonic()-start
    result['initial_model'] = api('/modelo').json()
    families = [r['familia_id'] for r in json.loads(Path('data/ejemplos/prediccion_valida.json').read_text())['familias']]
    payload = {'tienda_id': 1, 'fecha': '2026-03-01', 'familias': [{'familia_id': f, 'en_promocion': 0} for f in families]}
    pred = api('/v1/prediccion', payload); assert pred.status_code == 200, pred.text
    observed = {'tienda_id': 1, 'fecha': payload['fecha'], 'ventas': [
        {'familia_id': p['familia_id'], 'ventas': round(p['venta_esperada'])} for p in pred.json()['predicciones']]}
    assert api('/v1/observaciones', observed).json()['registros_guardados'] == 12
    assert api('/v1/observaciones', observed).json()['registros_guardados'] == 0
    assert api('/admin/reentrenar/desconocido').status_code == 404
    start = time.monotonic()
    run = api('/admin/reentrenar', {}); assert run.status_code == 202, run.text
    run_id = run.json()['id']
    duplicate = api('/admin/reentrenar', {}); assert duplicate.json()['id'] == run_id
    status = lambda: api('/admin/reentrenar/'+run_id).json()
    inference_statuses = []
    probe = {**payload, 'fecha':'2026-03-02'}
    def finished():
        inference_statuses.append(api('/v1/prediccion', probe).status_code)
        return status()['estado'] != 'en_curso'
    result['dag_poll_seconds'] = wait_for(finished, 600)
    result['inference_statuses_during_training'] = inference_statuses
    assert inference_statuses and all(code == 200 for code in inference_statuses)
    result['run_seconds_including_submission'] = time.monotonic()-start
    result['run_id'], result['run_result'] = run_id, status()
    assert status()['estado'] == 'exitoso', status()
    assert status()['promovido'] is True, status()
    result['reload_after_terminal_seconds'] = wait_for(lambda: api('/modelo').json()['version'] == status()['version'])
    save()
    payload['fecha'] = '2026-03-02'
    reference = api('/v1/prediccion', payload).json()
    assert 'predicciones' in reference
    # Segundo disparo real: sin nuevas fechas, no repetir ajuste ni promoción.
    second = api('/admin/reentrenar', {}).json()['id']
    result['no_new_data_seconds'] = wait_for(lambda: api('/admin/reentrenar/'+second).json()['estado'] != 'en_curso', 600)
    result['no_new_data_result'] = api('/admin/reentrenar/'+second).json()
    assert result['no_new_data_result']['promovido'] is False
    save()
    docker('stop', 'mlflow')
    result['mlflow_down_detection_seconds'] = wait_for(lambda: 'MLflow' in api('/health').json().get('motivo',''), 59)
    assert api('/v1/prediccion', payload).json() == reference
    # Fallo real de entrenamiento: Registry no disponible, un reintento y finalización.
    failed = api('/admin/reentrenar', {}); assert failed.status_code == 202
    failed_id = failed.json()['id']
    result['failed_run_id'] = failed_id
    result['failed_run_seconds'] = wait_for(lambda: api('/admin/reentrenar/'+failed_id).json()['estado'] != 'en_curso', 600)
    result['failed_result'] = api('/admin/reentrenar/'+failed_id).json()
    assert result['failed_result']['estado'] == 'fallido'
    assert result['failed_result']['promovido'] is False
    save()
    assert api('/v1/prediccion', payload).json() == reference
    docker('start', 'mlflow')
    result['mlflow_recovery_seconds'] = wait_for(lambda: api('/health').json().get('estado') == 'ok', 119)
    save()
    docker('stop', 'airflow')
    assert api('/admin/reentrenar', {}).status_code == 503
    assert 'Airflow' in api('/health').json()['motivo']
    assert api('/v1/prediccion', payload).json() == reference
    docker('start', 'airflow')
    result['airflow_recovery_seconds'] = wait_for(lambda: api('/health').json().get('estado') == 'ok', 119)
    save()
    before = docker('exec', '-T', 'postgres', 'psql', '-U', 'lab02', '-d', 'lab02', '-Atc',
                    'SELECT count(*) FROM observaciones; SELECT count(*) FROM ejecuciones;')
    docker('down')
    start = time.monotonic(); docker('up', '-d', '--no-build')
    wait_for(lambda: api('/health').json().get('estado') == 'ok', 600)
    result['warm_start_seconds'] = time.monotonic()-start
    after = docker('exec', '-T', 'postgres', 'psql', '-U', 'lab02', '-d', 'lab02', '-Atc',
                   'SELECT count(*) FROM observaciones; SELECT count(*) FROM ejecuciones;')
    assert before == after
    assert api('/modelo').json()['version'] == reference['version_modelo']
    assert api('/admin/reentrenar/'+run_id).json() == result['run_result']
    result['persistent_counts'] = [int(x) for x in after.split()]
    result['final_health'] = api('/health').json()
    save(); print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
