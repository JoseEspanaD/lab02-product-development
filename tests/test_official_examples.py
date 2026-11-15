"""Lee ejemplos docentes locales sin copiarlos ni publicarlos en el repositorio."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from novamercado.api import create_app
from novamercado.data import load_data
from test_api import MemoryRepository, TestModel


@pytest.mark.parametrize("code,expected", [(1, 200), (2, 200), (3, 200), (4, 200),
                                           (5, 422), (6, 422), (7, 200), (8, 422),
                                           (9, 200), (10, 422)])
def test_official_error_examples(code, expected):
    directory = Path("data/ejemplos/errores")
    if not directory.exists():
        pytest.skip("Ejemplos docentes no disponibles localmente")
    path = next(directory.glob(f"E{code:02d}_*.json"))
    payload = json.loads(path.read_text())
    data = load_data("data")
    with TestClient(create_app(data, MemoryRepository(), TestModel())) as client:
        endpoint = "/v1/prediccion" if code < 8 else "/v1/observaciones"
        response = client.post(endpoint, json=payload)
        assert response.status_code == expected
        if code == 9:
            assert client.post(endpoint, json=payload).json()["registros_guardados"] == 0
