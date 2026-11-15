"""Arranque vacío en proyecto nuevo; no elimina volúmenes. Ejecutar sin otros stacks del lab."""
import argparse
import json
from pathlib import Path
import subprocess
import time

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--api-url', required=True)
    parser.add_argument('--output', default='outputs/fase4_arranque_vacio.json')
    args = parser.parse_args()
    compose = ['docker', 'compose', '--env-file', args.env_file]
    existing = subprocess.check_output(compose+['ps', '-aq'], text=True)
    if existing.strip():
        raise SystemExit('Usar proyecto nuevo para afirmar arranque vacío')
    start = time.monotonic()
    subprocess.run(compose+['up','-d','--no-build'], check=True)
    while time.monotonic()-start < 600:
        try:
            health = requests.get(args.api_url+'/health', timeout=10).json()
            if health.get('estado') == 'ok':
                break
        except (requests.RequestException, ValueError):
            pass
        time.sleep(2)
    else:
        raise AssertionError('Arranque excedió 10 minutos')
    elapsed = time.monotonic()-start
    assert elapsed < 600
    model = requests.get(args.api_url+'/modelo', timeout=10).json()
    assert model['version'] == '1'
    bootstrap = subprocess.check_output(compose+['logs','--no-log-prefix','bootstrap'], text=True)
    reports = [json.loads(line) for line in bootstrap.splitlines() if line.startswith('{"trained":')]
    assert reports[-1]['trained'] and reports[-1]['imported']
    result = {'seconds': elapsed, 'health': health, 'model': model,
              'bootstrap_trained': True, 'bootstrap_imported': True}
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
