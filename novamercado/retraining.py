"""Trabajo idempotente de Airflow. Fechas derivadas de datos, nunca del reloj."""
import hashlib
import os
import tempfile
from dataclasses import replace

import pandas as pd

from .data import KEY
from .repository import PostgresRepository
from .registry import Registry
from .training import train_candidate


def merge_observations(data, observations):
    observations = observations.copy()
    observations['fecha'] = pd.to_datetime(observations.fecha)
    # Una corrección de ventas históricas puede usar la promoción publicada.
    original_promos = data.history[KEY + ['en_promocion']].rename(columns={'en_promocion': 'publicada'})
    observations = observations.merge(original_promos, on=KEY, how='left')
    observations['en_promocion'] = observations.en_promocion.fillna(observations.publicada)
    missing = observations.en_promocion.isna()
    usable = observations.loc[~missing, [*KEY, 'ventas', 'en_promocion']]
    h = pd.concat([data.history, usable], ignore_index=True).drop_duplicates(KEY, keep='last')
    # Las ventas sin promoción siguen sirviendo como lags en inferencia, pero no
    # como etiquetas supervisadas: no inventar el valor de la feature faltante.
    h = h.sort_values(KEY).reset_index(drop=True)
    digest = hashlib.sha256(h.to_csv(index=False, date_format='%Y-%m-%d').encode()).hexdigest()
    return replace(data, history=h), {'observations_received': len(observations),
        'observations_used': len(usable), 'observations_missing_promotions': int(missing.sum()),
        'snapshot_sha256': digest, 'validation_end': str(h.fecha.max().date())}


def execute(run_id, repository, registry):
    with repository.model_lock():
        saved = repository.execution(run_id)
        if saved and saved['resultado']:
            return saved['resultado']
        current = registry.current()
        if current is None:
            raise RuntimeError('No existe champion')
        repository.save_execution(run_id, str(current.version))
        # Recuperar registro completado antes de una interrupción, sin repetir ajuste.
        versions = [v for v in registry.versions() if v.tags.get('execution_id') == run_id]
        with tempfile.TemporaryDirectory() as directory:
            if versions:
                version = max(versions, key=lambda v: int(v.version))
                registry.load(version.version, directory)
                promoted = version.tags.get('eligible') == 'true'
                if promoted and str(current.version) != str(version.version):
                    if str(current.version) != version.tags['incumbent_version']:
                        raise RuntimeError('Vigente cambiado durante recuperación; no promover')
                    registry.promote(version.version)
                result = {'estado': 'exitoso', 'promovido': promoted,
                          'version': str(version.version if promoted else current.version),
                          'motivo': version.tags['promotion_reason']}
            else:
                data = repository.load_data()
                observed = repository.observations_before('9999-12-31')
                data, lineage = merge_observations(data, observed)
                incumbent = registry.load(current.version, directory)
                end = pd.Timestamp(lineage['validation_end'])
                # Sin una ventana nueva suficiente no hay un candidato evaluable.
                if end - pd.Timedelta(days=59) < pd.Timestamp(incumbent.available_from):
                    result = {'estado': 'exitoso', 'promovido': False, 'version': str(current.version),
                              'motivo': 'Datos nuevos insuficientes para validación posterior al vigente'}
                else:
                    artifact, report, example = train_candidate(data, end, incumbent)
                    report.update({'execution_id': run_id, 'incumbent_version': str(current.version),
                                   'operational_lineage': lineage})
                    version = registry.register(artifact, report, example)
                    registry.load(version.version, directory)
                    if report['eligible']:
                        registry.promote(version.version)
                    result = {'estado': 'exitoso', 'promovido': report['eligible'],
                              'version': str(version.version if report['eligible'] else current.version),
                              'motivo': report['reason']}
            repository.finish_execution(run_id, result)
            return result


def main():
    import sys
    repository = PostgresRepository(os.environ['DATABASE_URL'])
    registry = Registry(os.environ['MLFLOW_TRACKING_URI'])
    run_id = os.environ['RETRAIN_RUN_ID']
    if sys.argv[1:] == ['finalize']:
        saved = repository.execution(run_id)
        if saved and not saved['resultado']:
            repository.finish_execution(run_id, {'estado': 'fallido', 'promovido': False,
                'version': saved['version_inicial'], 'motivo': 'Entrenamiento fallido; consultar logs de Airflow'})
            raise SystemExit(1)
        if saved and saved['resultado'] and saved['resultado']['estado'] == 'fallido':
            raise SystemExit(1)
    else:
        execute(run_id, repository, registry)


if __name__ == '__main__':
    main()
