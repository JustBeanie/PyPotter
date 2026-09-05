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
    log_level: str = "INFO"

    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'pypotter.db').as_posix()}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
