"""Evidencia de configuración, estados reales, linaje y caída de DB de Airflow."""
import argparse
import json
from pathlib import Path
import subprocess
import time

from dotenv import dotenv_values
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--output', default='outputs/fase4_detalles.json')
    args = parser.parse_args()
    env = dotenv_values(args.env_file)
    airflow = 'http://127.0.0.1:'+env.get('AIRFLOW_PORT','8080')
    mlflow = 'http://127.0.0.1:'+env.get('MLFLOW_PORT','5000')
    api = 'http://127.0.0.1:'+env.get('API_PORT','8000')
    auth = (env.get('AIRFLOW_USERNAME','lab02'),env['AIRFLOW_PASSWORD'])
    dag_url = airflow+'/api/v1/dags/novamercado_reentrenar'
    dag = requests.get(dag_url,auth=auth,timeout=10).json()
    tasks = requests.get(dag_url+'/tasks',auth=auth,timeout=10).json()['tasks']
    assert dag['schedule_interval'] is None and dag['max_active_runs']==1
    assert {t['task_id'] for t in tasks}=={'entrenar_evaluar_promover','finalizar'}
    assert all(t['retries']==1 for t in tasks)
    runs = requests.get(dag_url+'/dagRuns',auth=auth,timeout=10).json()['dag_runs']
    assert len(runs)==3
    failed = [r for r in runs if r['state']=='failed']; assert len(failed)==1
    instances = requests.get(dag_url+'/dagRuns/'+failed[0]['dag_run_id']+'/taskInstances',auth=auth,timeout=10).json()['task_instances']
    assert all(t['state']=='failed' for t in instances)
    version = requests.get(mlflow+'/api/2.0/mlflow/model-versions/get',params={'name':'novamercado','version':'2'},timeout=10).json()['model_version']
    run = requests.get(mlflow+'/api/2.0/mlflow/runs/get',params={'run_id':version['run_id']},timeout=10).json()['run']
    params = {p['key']:p['value'] for p in run['data']['params']}
    metrics = {m['key']:m['value'] for m in run['data']['metrics']}
    assert params['observations_used']=='12'
    assert metrics['candidate_costo_total'] < metrics['incumbent_costo_total']
    assert metrics['candidate_costo_total'] < metrics['baseline_costo_total']
    assert len(run['inputs']['dataset_inputs'])==6
    # La caída de metadatos Airflow no impide inferencia del producto.
    families = [x['familia_id'] for x in json.loads(Path('data/ejemplos/prediccion_valida.json').read_text())['familias']]
    payload={'tienda_id':1,'fecha':'2026-03-02','familias':[{'familia_id':f,'en_promocion':0} for f in families]}
    reference=requests.post(api+'/v1/prediccion',json=payload,timeout=10).json()
    compose=['docker','compose','--env-file',args.env_file]
    subprocess.run(compose+['stop','airflow-db'],check=True)
    try:
        health=requests.get(api+'/health',timeout=20).json()
        assert health['estado']=='degradado' and 'Airflow' in health['motivo']
        assert requests.post(api+'/admin/reentrenar',timeout=20).status_code==503
        assert requests.post(api+'/v1/prediccion',json=payload,timeout=20).json()==reference
    finally:
        subprocess.run(compose+['start','airflow-db'],check=True)
    start=time.monotonic()
    while time.monotonic()-start<120:
        if requests.get(api+'/health',timeout=20).json().get('estado')=='ok':
            break
        time.sleep(2)
    else:
        raise AssertionError('No recuperó Airflow tras DB')
    result={'dag':{k:dag[k] for k in ['dag_id','schedule_interval','max_active_runs']},
            'task_ids':[t['task_id'] for t in tasks],
            'runs':[{'id':r['dag_run_id'],'state':r['state']} for r in runs],
            'failed_task_attempts':[{k:t[k] for k in ['task_id','state','try_number']} for t in instances],
            'model_run_id':version['run_id'],'metrics':metrics,
            'operational_lineage':{k:params[k] for k in ['observations_used','observations_received','observations_missing_promotions','snapshot_sha256','validation_end']},
            'dataset_inputs':6,'airflow_db_recovery_seconds':time.monotonic()-start}
    Path(args.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
