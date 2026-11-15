"""Adaptador de la API REST estable de Airflow; nunca entrena en FastAPI."""
import uuid
from urllib.parse import quote

import requests

from .providers import Unavailable
from .schemas import RunStatus

DAG_ID = "novamercado_reentrenar"


class AirflowAdministration:
    def __init__(self, provider, repository, url, username, password):
        self.provider, self.repository = provider, repository
        self.url, self.auth = url.rstrip('/'), (username, password)

    def request(self, method, path, **kwargs):
        try:
            response = requests.request(method, self.url + path, auth=self.auth,
                                        timeout=(2, 4), **kwargs)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise Unavailable("Airflow no disponible") from exc

    def healthy(self):
        try:
            health = self.request('GET', '/health')
            dag = self.request('GET', f'/api/v1/dags/{DAG_ID}')
            return bool(health and dag and not dag['is_paused'] and
                        all(health[k]['status'] == 'healthy' for k in ['metadatabase', 'scheduler']))
        except (Unavailable, KeyError, TypeError):
            return False

    def dependencies(self):
        return {'MLflow': self.provider.healthy(), 'Airflow': self.healthy()}

    def start(self):
        if not self.healthy():
            raise Unavailable('Airflow o su DAG no disponible')
        with self.repository.submission_lock():
            runs = self.request('GET', f'/api/v1/dags/{DAG_ID}/dagRuns',
                                params={'state': ['queued', 'running'], 'limit': 100})
            if runs is None:
                raise Unavailable('DAG no disponible')
            if runs['dag_runs']:
                return runs['dag_runs'][0]['dag_run_id']
            run_id = 'api__' + uuid.uuid4().hex
            info = self.provider.info()
            self.repository.save_execution(run_id, info.version if info else '')
            created = self.request('POST', f'/api/v1/dags/{DAG_ID}/dagRuns',
                                   json={'dag_run_id': run_id, 'conf': {}})
            if created is None:
                raise Unavailable('No se pudo iniciar el DAG')
            return created['dag_run_id']

    def status(self, run_id):
        run = self.request('GET', f'/api/v1/dags/{DAG_ID}/dagRuns/{quote(run_id, safe="")}')
        if run is None:
            return None
        if run['state'] not in ['success', 'failed']:
            return RunStatus(estado='en_curso')
        result = self.repository.execution(run_id)
        if result and result['resultado']:
            return RunStatus(**result['resultado'])
        # También cubre timeout global/scheduler caído antes de ejecutar el finalizador.
        version = result['version_inicial'] if result else ''
        return RunStatus(estado='fallido', promovido=False, version=version,
                         motivo='Airflow terminó sin resultado confirmado; consultar logs del DAG')
