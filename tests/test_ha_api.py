import base64
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from pypotter.api.app import create_app
from pypotter.config import Settings


def test_token_protects_api_but_keeps_standalone_gui_available(tmp_path):
    settings = Settings(
        data_dir=tmp_path, training_dir=tmp_path / "Training", api_token="test-token"
    )
    client = TestClient(create_app(settings))
    assert client.get("/").status_code == 200
    assert client.get("/ready").status_code == 200
    for endpoint in ("/api/v1/instance", "/api/v1/spells", "/api/v1/recognitions"):
        denied = client.get(endpoint)
        assert denied.status_code == 401
        assert denied.headers["WWW-Authenticate"] == "Bearer"
        assert client.get(endpoint, headers={"Authorization": "Bearer invalid"}).status_code == 401
        assert (
            client.get(endpoint, headers={"Authorization": "Bearer test-token"}).status_code == 200
        )


def test_camera_uses_trained_spells_and_shares_history_and_mqtt(tmp_path):
    settings = Settings(
        data_dir=tmp_path, training_dir=tmp_path / "Training", api_token="test-token"
    )
    app = create_app(settings)
    client = TestClient(app, headers={"Authorization": "Bearer test-token"})
    published = []

    class Publisher:
        def publish_recognition(self, recognition, *, recognition_id):
            published.append((recognition, recognition_id))

        def update_spells(self, spells):
            assert "lumos_iris" in spells

    app.state.mqtt_publisher = Publisher()
    assert client.get("/api/v1/instance").json()["mqtt_topic_prefix"] == "pypotter"
    image = np.zeros((50, 50), dtype=np.uint8)
    cv2.line(image, (11, 37), (31, 7), 255, 4)
    success, encoded = cv2.imencode(".png", image)
    assert success
    sample = base64.b64encode(encoded.tobytes()).decode("ascii")
    camera_path = "/api/v1/camera/recognitions"

    assert (
        client.post(
            "/api/v1/spells/train", json={"name": "Lumos Iris", "images": [sample]}
        ).status_code
        == 201
    )
    camera = client.post(camera_path, json={"image_base64": sample})
    assert camera.status_code == 201
    cast = camera.json()
    assert cast["spell"] == "lumos_iris"
    assert cast["source"] == "camera"
    assert cast["created_at"].endswith("Z")
    assert published[0][0].source == "camera"
    assert published[0][1] == cast["id"]

    mistake = next((settings.training_dir / "mistakes").glob("*.png"))
    rejected = client.post(
        camera_path, json={"image_base64": base64.b64encode(mistake.read_bytes()).decode("ascii")}
    )
    assert rejected.status_code == 204
    assert len(published) == 1
    assert client.get("/api/v1/recognitions").json() == {"items": [cast]}


def test_wand_tracker_reads_optical_flow_points(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parent.parent))
    from PyPotter import WandTracker

    tracker = WandTracker()
    frame = np.zeros((64, 64), dtype=np.uint8)
    cv2.rectangle(frame, (20, 20), (28, 28), 255, -1)
    assert tracker.update(cv2, frame) is None
    assert tracker.update(cv2, np.roll(frame, 3, axis=1)) is None
    assert tracker.path
    assert len(tracker.path[0]) == 2
