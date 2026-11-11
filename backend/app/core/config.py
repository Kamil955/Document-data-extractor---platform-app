from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables only (12-factor style)."""

    model_config = SettingsConfigDict(extra="ignore")

    # "+psycopg" selects the psycopg 3 driver. The same URL works for the async
    # engine (the app) and the sync engine (Alembic).
    database_url: str = "postgresql+psycopg://contract:contract@localhost:5432/contract"


@lru_cache
def get_settings() -> Settings:
    # Cached so the environment is parsed once, not on every request.
    return Settings()
