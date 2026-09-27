"""Configuration, loaded from the environment. No secret is ever hard-coded."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(REPO_ROOT / ".env"), extra="ignore")

    app_name: str = "SkyGuard AI"
    environment: str = "development"

    database_url: str = "postgresql+psycopg://skyguard:skyguard_dev_pw@127.0.0.1:5432/skyguard"

    supertokens_connection_uri: str = "https://try.supertokens.com"
    supertokens_api_key: str = ""

    api_domain: str = "http://localhost:8000"
    website_domain: str = "http://localhost:5173"

    model_dir: Path = REPO_ROOT / "models"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
