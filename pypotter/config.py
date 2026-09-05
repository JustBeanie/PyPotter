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
    enable_mqtt: bool = False
    log_level: str = "INFO"

    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'pypotter.db').as_posix()}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
