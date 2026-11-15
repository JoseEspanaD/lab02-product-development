"""Disparo por API; no asociar fechas simuladas con el calendario del scheduler."""
from datetime import datetime, timedelta, timezone

from airflow import DAG
from airflow.operators.bash import BashOperator

COMMAND = ('cd /opt/product-app && '
           'PYTHONHOME=/opt/product LD_LIBRARY_PATH=/opt/product/lib '
           '/opt/product/bin/python -m novamercado.retraining')

with DAG('novamercado_reentrenar', schedule=None, catchup=False,
         start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
         max_active_runs=1, max_active_tasks=1, dagrun_timeout=timedelta(minutes=9),
         is_paused_upon_creation=False, default_args={'retries': 1,
             'retry_delay': timedelta(seconds=10), 'execution_timeout': timedelta(minutes=4)}) as dag:
    train = BashOperator(task_id='entrenar_evaluar_promover', bash_command=COMMAND,
                         env={'RETRAIN_RUN_ID': '{{ run_id }}'}, append_env=True)
    finalize = BashOperator(task_id='finalizar', bash_command=COMMAND + ' finalize',
                            env={'RETRAIN_RUN_ID': '{{ run_id }}'}, append_env=True,
                            trigger_rule='all_done', retries=1, execution_timeout=timedelta(seconds=30))
    train >> finalize
