from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
import requests

from novamercado.airflow_client import AirflowAdministration
from novamercado.data import Data
from novamercado.providers import Unavailable
from novamercado.retraining import merge_observations, execute


def test_merge_observation_precedence_and_missing_promotions(history, stores, holidays, costs):
    data = Data(history, stores, pd.DataFrame({'familia_id': ['pan']}), holidays, costs, {})
    observations = pd.DataFrame([
        {'fecha': '2024-01-01', 'tienda_id': 1, 'familia_id': 'pan', 'ventas': 999, 'en_promocion': None},
        {'fecha': '2024-03-10', 'tienda_id': 1, 'familia_id': 'pan', 'ventas': 33, 'en_promocion': None},
        {'fecha': '2024-03-11', 'tienda_id': 1, 'familia_id': 'pan', 'ventas': 44, 'en_promocion': 8},
    ])
    updated, lineage = merge_observations(data, observations)
    first = updated.history.query('tienda_id==1').iloc[0]
    assert first.ventas == 999 and first.en_promocion == 0
    assert updated.history.iloc[-1].en_promocion == 8
    assert lineage['observations_used'] == 2
    assert lineage['observations_missing_promotions'] == 1
    assert lineage['validation_end'] == '2024-03-11'
    assert history.iloc[0].ventas == 1
    assert merge_observations(data, observations.iloc[::-1])[1]['snapshot_sha256'] == lineage['snapshot_sha256']


@pytest.fixture
def admin():
    provider = Mock(); provider.info.return_value = SimpleNamespace(version='7')
    repo = Mock(); repo.submission_lock.side_effect = lambda: nullcontext()
    return AirflowAdministration(provider, repo, 'http://airflow:8080', 'user', 'password')


def test_start_real_run_and_duplicate_active(admin):
    admin.healthy = lambda: True
    admin.request = Mock(side_effect=[{'dag_runs': []}, {'dag_run_id': 'created'}])
    assert admin.start() == 'created'
    assert admin.request.call_args.kwargs['json']['conf'] == {}
    admin.request = Mock(return_value={'dag_runs': [{'dag_run_id': 'active'}]})
    assert admin.start() == 'active'
    assert admin.request.call_count == 1


@pytest.mark.parametrize('state,expected', [('queued','en_curso'), ('running','en_curso'), ('success','exitoso'), ('failed','fallido')])
def test_status_contract(admin, state, expected):
    admin.request = Mock(return_value={'state': state})
    admin.repository.execution.return_value = {'resultado': {'estado': expected, 'promovido': False,
                                                            'version': '7', 'motivo': 'prueba'}}
    assert admin.status('run').estado == expected


def test_unknown_and_unavailable(admin, monkeypatch):
    admin.request = Mock(return_value=None)
    assert admin.status('unknown') is None
    admin = AirflowAdministration(Mock(), Mock(), 'http://airflow', 'u', 'p')
    monkeypatch.setattr(requests, 'request', Mock(side_effect=requests.Timeout))
    assert admin.healthy() is False
    with pytest.raises(Unavailable):
        admin.start()
    with pytest.raises(Unavailable):
        admin.status('run')


def test_retry_finished_execution_does_not_train():
    repo, registry = Mock(), Mock()
    repo.model_lock.return_value = nullcontext()
    repo.execution.return_value = {'resultado': {'estado': 'exitoso', 'version': '2'}}
    assert execute('run', repo, registry)['version'] == '2'
    registry.current.assert_not_called()


def test_recover_registered_version_without_training():
    repo, registry = Mock(), Mock()
    repo.model_lock.return_value = nullcontext()
    repo.execution.return_value = {'resultado': None}
    registry.current.return_value = SimpleNamespace(version='1')
    registry.versions.return_value = [SimpleNamespace(version='2', tags={
        'execution_id': 'run', 'eligible': 'true', 'incumbent_version': '1', 'promotion_reason': 'mejor'})]
    result = execute('run', repo, registry)
    assert result['version'] == '2' and result['promovido']
    registry.promote.assert_called_once_with('2')
    repo.load_data.assert_not_called()


def test_recover_does_not_overwrite_newer_champion():
    repo, registry = Mock(), Mock()
    repo.model_lock.return_value = nullcontext()
    repo.execution.return_value = {'resultado': None}
    registry.current.return_value = SimpleNamespace(version='3')
    registry.versions.return_value = [SimpleNamespace(version='2', tags={
        'execution_id': 'run', 'eligible': 'true', 'incumbent_version': '1'})]
    with pytest.raises(RuntimeError, match='Vigente cambiado'):
        execute('run', repo, registry)
    registry.promote.assert_not_called()


def test_failed_task_result_survives_airflow_success_leaf(admin):
    admin.request = Mock(return_value={'state': 'failed'})
    admin.repository.execution.return_value = {'resultado': {'estado': 'fallido', 'promovido': False,
        'version': '7', 'motivo': 'Entrenamiento fallido'}}
    assert admin.status('run').version == '7'


def test_terminal_without_result_is_not_success(admin):
    admin.request = Mock(return_value={'state': 'success'})
    admin.repository.execution.return_value = {'resultado': None, 'version_inicial': '7'}
    assert admin.status('run').estado == 'fallido'
