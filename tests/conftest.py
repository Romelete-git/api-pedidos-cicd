import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Cada prueba usa una base de datos nueva y vacía
    monkeypatch.setenv("PEDIDOS_DB", str(tmp_path / "pruebas.db"))
    from main import app

    with TestClient(app) as cliente:
        yield cliente
