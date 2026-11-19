import base64

import cv2
import numpy as np
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from pypotter.api.app import create_app
from pypotter.config import Settings


@pytest.fixture()
def client(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        training_dir=tmp_path / "Training",
    )
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
    assert "spell" in response.json()["message"].lower()


def test_custom_spell_training_is_available_for_casting_and_image_recognition(client):
    image = np.zeros((50, 50), dtype=np.uint8)
    cv2.line(image, (5, 40), (40, 5), 255, 4)
    success, encoded = cv2.imencode(".png", image)
    assert success
    sample = "data:image/png;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")

    trained = client.post(
        "/api/v1/spells/train", json={"name": "Lumos Maxima", "images": [sample]}
    )
    assert trained.status_code == 201
    assert trained.json() == {"spell": "lumos_maxima", "added": 1}
    assert "lumos_maxima" in client.get("/api/v1/spells").json()
    assert client.post("/api/v1/recognitions", json={"spell": "Lumos Maxima"}).json()[
        "spell"
    ] == "lumos_maxima"
    recognized = client.post("/api/v1/recognitions", json={"image_base64": sample})
    assert recognized.status_code == 201
    assert recognized.json()["spell"] == "lumos_maxima"


def test_invalid_training_batch_does_not_create_a_spell(client):
    response = client.post(
        "/api/v1/spells/train", json={"name": "../bad", "images": ["not-an-image"]}
    )
    assert response.status_code == 422
    assert "bad" not in client.get("/api/v1/spells").json()
