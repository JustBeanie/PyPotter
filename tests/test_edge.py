import base64
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient

from pypotter.api.app import create_app
from pypotter.config import Settings
from pypotter.services.processor import ProcessingError, SpellProcessor


def test_headless_mode_serves_api_without_web_interface(tmp_path):
    settings = Settings(data_dir=tmp_path, training_dir=tmp_path / "Training")
    with TestClient(create_app(settings, ui_enabled=False)) as client:
        assert client.get("/").status_code == 404
        assert client.get("/docs").status_code == 404
        assert client.get("/ready").status_code == 200
        assert client.post("/api/v1/recognitions", json={"spell": "incendio"}).status_code == 201


def test_spell_requests_have_single_admission_slot(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, training_dir=tmp_path / "Training")
    app = create_app(settings)
    process = app.state.processor.process
    entered, release = Event(), Event()

    def slow_process(spell, image_base64):
        entered.set()
        assert release.wait(5)
        return process(spell, image_base64)

    monkeypatch.setattr(app.state.processor, "process", slow_process)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(client.post, "/api/v1/recognitions", json={"spell": "incendio"})
        try:
            assert entered.wait(5)
            busy = client.post("/api/v1/spells/train", json={"name": "lumos", "images": ["x"]})
            assert busy.status_code == 503
            assert busy.json()["code"] == "spell_busy"
            assert client.get("/ready").status_code == 200
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 201
        assert client.post("/api/v1/recognitions", json={"spell": "incendio"}).status_code == 201


def test_oversized_image_dimensions_rejected_before_importing_decoder(tmp_path, monkeypatch):
    def decoder_forbidden():
        raise AssertionError("Decoder should not be loaded")

    monkeypatch.setattr("pypotter.services.processor.opencv", decoder_forbidden)
    png_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"
    sample = base64.b64encode(png_header + (50_000).to_bytes(4, "big") * 2).decode()
    with pytest.raises(ProcessingError, match="dimensions are too large"):
        SpellProcessor(tmp_path).decode_image(sample)
