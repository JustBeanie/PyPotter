import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from pypotter.api.app import create_app
from pypotter.config import Settings


@pytest.fixture()
def client(tmp_path):
    settings = Settings(data_dir=tmp_path, database_url=f"sqlite:///{tmp_path / 'test.db'}")
    return TestClient(create_app(settings))


def test_health_and_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json()["status"] == "ready"


def test_recognition_is_persisted_and_returned_in_history(client):
    response = client.post("/api/v1/recognitions", json={"spell": "incendio"})
    assert response.status_code == 201
    assert response.json()["spell"] == "incendio"
    assert client.get("/api/v1/recognitions").json()["items"][0]["spell"] == "incendio"


def test_invalid_recognition_is_readable(client):
    response = client.post("/api/v1/recognitions", json={"spell": "not-a-spell"})
    assert response.status_code == 422
    assert "validation" in response.json()["code"]
