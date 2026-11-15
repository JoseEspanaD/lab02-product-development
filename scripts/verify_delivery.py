"""Operación de varios días y fallos adicionales sobre un proyecto exclusivo de pruebas.

Ejecutar después de verify_airflow.py y verify_airflow_details.py; conserva volúmenes.
"""
import argparse
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import time

from dotenv import dotenv_values
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--output', default='outputs/fase5_operacion.json')
    args = parser.parse_args()
    env = dotenv_values(args.env_file)
    if not env.get('COMPOSE_PROJECT_NAME', '').startswith('lab02fase5'):
        raise SystemExit('Reservado a un proyecto aislado lab02fase5*')
    base = 'http://127.0.0.1:' + env['API_PORT']
    compose = ['docker', 'compose', '--env-file', args.env_file]

    def docker(*cmd):
        return subprocess.check_output(compose + list(cmd), text=True)

    def call(path, body=None):
        response = (requests.get(base+path, timeout=20) if body is None else
                    requests.post(base+path, json=body, timeout=20))
        return response

    def wait(predicate, limit=120):
        start = time.monotonic()
        while time.monotonic()-start < limit:
            try:
                if predicate():
                    return time.monotonic()-start
            except requests.RequestException:
                pass
            time.sleep(2)
        raise AssertionError('Tiempo límite excedido')

    def counts():
        return docker('exec', '-T', 'postgres', 'psql', '-U', env.get('POSTGRES_USER','lab02'),
                      '-d', env.get('POSTGRES_DB','lab02'), '-Atc',
                      'SELECT count(*) FROM solicitudes; SELECT count(*) FROM predicciones; '
                      'SELECT count(*) FROM observaciones; SELECT count(*) FROM ejecuciones;')

    import csv
    with Path('data/familias.csv').open() as stream:
        families = [r['familia_id'] for r in csv.DictReader(stream)]
    payload = {'tienda_id':1, 'fecha':'2026-03-02',
               'familias':[{'familia_id':f,'en_promocion':0} for f in families]}
    reference = call('/v1/prediccion', payload)
    assert reference.status_code == 200, reference.text
    result = {'model':call('/modelo').json(), 'days':[], 'responses':{}}
    # Ventas sintéticas con cambio de escala; solo prueban operación, no precisión futura.
    for offset in range(5):
        day = str(date(2026,3,2)+timedelta(days=offset))
        saved = 0
        for store in (1,10):
            payload.update(tienda_id=store, fecha=day)
            pred = call('/v1/prediccion', payload)
            assert pred.status_code == 200, pred.text
            p = pred.json()
            assert len(p['predicciones']) == 12
            assert all(type(r['cantidad_sugerida']) is int and r['cantidad_sugerida'] >= 0
                       for r in p['predicciones'])
            assert call('/v1/prediccion', payload).json() == p
            observed = {'tienda_id':store,'fecha':day,'ventas':[
                {'familia_id':r['familia_id'],'ventas':round(r['venta_esperada']*(1.3+offset*.05))}
                for r in p['predicciones']]}
            response = call('/v1/observaciones',observed)
            assert response.status_code == 200, response.text
            assert response.json()['registros_guardados'] == 12
            assert call('/v1/observaciones', observed).json()['registros_guardados'] == 0
            observed['ventas'][0]['ventas'] += 1
            assert call('/v1/observaciones', observed).json()['registros_guardados'] == 1
            assert call('/v1/observaciones', observed).json()['registros_guardados'] == 0
            saved += 12
        result['days'].append({'date':day,'stores':[1,10],'new_observations':saved})
    payload.update(tienda_id=1,fecha='2026-03-07')
    reference = call('/v1/prediccion',payload).json()
    future = {'tienda_id':1,'fecha':'2026-03-20',
              'ventas':[{'familia_id':f,'ventas':99999} for f in families]}
    assert call('/v1/observaciones', future).json()['registros_guardados'] == 12
    assert call('/v1/prediccion',payload).json() == reference
    result['future_observations_do_not_change_past_prediction'] = True
    repaired = deepcopy(payload)
    repaired.update(tienda_id='T01',fecha='07/03/2026',extra='sin efecto')
    repaired['familias'][0].update(familia_id=families[0].upper(),en_promocion='0.0')
    response = call('/v1/prediccion', repaired)
    assert response.status_code == 200, response.text
    assert response.json()['calidad']['estado'] == 'advertencia'
    result['responses']['repaired_with_warning'] = response.json()
    invalid = []
    for field, value in [('fecha','2026-02-30'),('tienda_id',True),('familias',payload['familias'][:-1])]:
        case = deepcopy(payload); case[field] = value; invalid.append(case)
    case = deepcopy(payload); case['familias'][0]['en_promocion'] = 0.5; invalid.append(case)
    case = deepcopy(payload); dup = deepcopy(case['familias'][0]); dup['en_promocion']=5
    case['familias'].append(dup); invalid.append(case)
    result['responses']['rejections'] = []
    for case in invalid:
        response = call('/v1/prediccion',case)
        assert response.status_code == 422, response.text
        assert response.json()['detail']
        result['responses']['rejections'].append(response.json())
    before = counts()
    docker('stop','mlflow')
    try:
        result['mlflow_detection_seconds'] = wait(lambda:'MLflow' in call('/health').json().get('motivo',''),59)
        assert call('/v1/prediccion',payload).json() == reference
        docker('restart','api')
        result['offline_api_restart_seconds'] = wait(lambda:call('/modelo').status_code == 200)
        assert call('/v1/prediccion',payload).json() == reference
        assert call('/health').json()['estado'] == 'degradado'
    finally:
        docker('start','mlflow')
    result['mlflow_recovery_seconds'] = wait(lambda:call('/health').json().get('estado') == 'ok',119)
    docker('stop','postgres')
    try:
        assert 'PostgreSQL' in call('/health').json()['motivo']
        response = call('/v1/prediccion',payload)
        assert response.status_code == 503
        result['responses']['database_unavailable'] = response.json()
    finally:
        docker('start','postgres')
    result['product_database_recovery_seconds'] = wait(lambda:call('/health').json().get('estado') == 'ok',119)
    assert call('/v1/prediccion',payload).json() == reference
    result['counts_before_failures'] = [int(x) for x in before.split()]
    result['counts_after_failures'] = [int(x) for x in counts().split()]
    assert result['counts_after_failures'][2:] == result['counts_before_failures'][2:]
    assert call('/modelo').json() == result['model']
    result['health'] = call('/health').json()
    Path(args.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='responses'},indent=2))


if __name__ == '__main__':
    main()
