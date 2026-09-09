"""Environment-driven application configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PYPOTTER_", env_file=".env", extra="ignore")

    environment: str = "development"
    data_dir: Path = Path("./data")
    database_url: str | None = None
    training_dir: Path = Path("./Training")
    home_assistant_url: str | None = None
    home_assistant_token: str | None = Field(default=None, repr=False)
    enable_home_assistant: bool = False
    mqtt_host: str | None = None
    mqtt_port: int = Field(default=1883, ge=1, le=65535)
    mqtt_username: str | None = None
    mqtt_password: str | None = Field(default=None, repr=False)
    mqtt_discovery_prefix: str = "homeassistant"
    mqtt_topic_prefix: str = "pypotter"
    mqtt_client_id: str = "pypotter"
    mqtt_tls: bool = False
    enable_mqtt: bool = False
    log_level: str = "INFO"
    max_request_body_bytes: int = Field(default=8 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    max_image_bytes: int = Field(default=4 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    max_image_pixels: int = Field(default=25_000_000, ge=10_000, le=100_000_000)
    max_image_dimension: int = Field(default=10_000, ge=100, le=50_000)
    rate_limit_requests: int = Field(default=30, ge=1, le=10_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=86_400)

    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'pypotter.db').as_posix()}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
