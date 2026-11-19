import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pypotter.api.app import create_app
from pypotter.config import Settings
from pypotter.integrations.home_assistant import HomeAssistantClient, validate_home_assistant_url
from pypotter.services.processor import ProcessingError, SpellProcessor


def make_client(tmp_path: Path, **overrides) -> TestClient:
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'security.db'}",
        **overrides,
    )
    return TestClient(create_app(settings))


def test_security_headers_and_hsts_are_environment_appropriate(tmp_path):
    dev = make_client(tmp_path / "dev")
    response = dev.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert "Strict-Transport-Security" not in response.headers

    prod = make_client(tmp_path / "prod", environment="production")
    assert "max-age=63072000" in prod.get("/health").headers["Strict-Transport-Security"]


def test_readiness_failure_keeps_database_error_server_side(tmp_path, monkeypatch, caplog):
    client = make_client(tmp_path)

    def fail_connect(*args, **kwargs):
        raise RuntimeError("sensitive database connection details")

    monkeypatch.setattr("sqlalchemy.engine.Engine.connect", fail_connect)
    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert "sensitive database connection details" not in response.text
    assert "Readiness check failed" in caplog.text


def test_validation_error_does_not_echo_request_data(tmp_path):
    client = make_client(tmp_path)
    response = client.post("/api/v1/recognitions", json={"spell": ["sensitive-secret"]})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert "sensitive-secret" not in response.text
    assert all(
        "input" not in detail and "ctx" not in detail for detail in response.json()["details"]
    )


def test_request_body_limit_and_rate_limit(tmp_path):
    client = make_client(tmp_path, max_request_body_bytes=1024, rate_limit_requests=2)
    assert client.post("/api/v1/recognitions", json={"spell": "incendio"}).status_code == 201
    assert client.post("/api/v1/recognitions", json={"spell": "incendio"}).status_code == 201
    assert client.get("/api/v1/spells").status_code == 429

    limited = make_client(tmp_path / "large", max_request_body_bytes=1024)
    response = limited.post(
        "/api/v1/recognitions",
        content=b"{" + b"a" * 2000,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413


def test_home_assistant_url_policy_and_redirects(monkeypatch):
    assert validate_home_assistant_url("http://localhost:8123") == "http://localhost:8123"
    assert validate_home_assistant_url("https://ha.example.test") == "https://ha.example.test"
    for url in (
        "http://ha.example.test",
        "ftp://ha.example.test",
        "https://user:pass@ha.example.test",
    ):
        with pytest.raises(ValueError):
            validate_home_assistant_url(url)

    captured = {}

    def fake_post(*args, **kwargs):
        captured.update(kwargs)
        return type(
            "Response",
            (),
            {"content": b"", "raise_for_status": lambda self: None, "json": lambda self: {}},
        )()

    monkeypatch.setattr("pypotter.integrations.home_assistant.requests.post", fake_post)
    HomeAssistantClient("https://ha.example.test", "secret").trigger_spell("incendio")
    assert captured["allow_redirects"] is False


def test_image_limits_and_magic_bytes_are_enforced(tmp_path):
    processor = SpellProcessor(tmp_path, max_image_bytes=10)
    with pytest.raises(ProcessingError, match="too large"):
        processor.process(image_base64=base64.b64encode(b"x" * 20).decode())
    processor = SpellProcessor(tmp_path)
    with pytest.raises(ProcessingError, match="PNG and JPEG"):
        processor.process(image_base64="bm90IGFuIGltYWdl")
