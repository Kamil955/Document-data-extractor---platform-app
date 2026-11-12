from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables only (12-factor style)."""

    model_config = SettingsConfigDict(extra="ignore")

    # "+psycopg" selects the psycopg 3 driver. The same URL works for the async
    # engine (the app) and the sync engine (Alembic).
    database_url: str = "postgresql+psycopg://contract:contract@localhost:5432/contract"

    # The default points at the local floci-az emulator. floci-az does not validate
    # credentials, so the key is only valid base64 ("local-dev-key"), not a secret.
    # In docker compose the endpoint host is the service name (floci-az), not localhost.
    azure_storage_connection_string: str = (
        "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
        "AccountKey=bG9jYWwtZGV2LWtleQ==;"
        "BlobEndpoint=http://localhost:4577/devstoreaccount1;"
    )
    blob_container: str = "documents"

    # Embeddings come from a local Ollama server. In docker compose the worker runs with
    # host networking, so "localhost" reaches the Ollama running on the host machine.
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "qwen3-embedding:0.6b"

    # Chunking, in characters (see ingestion/chunking.py for the reasoning).
    chunk_max_chars: int = 1500
    chunk_overlap_chars: int = 200

    # Worker behaviour.
    worker_poll_seconds: float = 2.0  # sleep when there is nothing to do
    worker_backoff_seconds: float = 15.0  # sleep when Ollama is unavailable
    worker_stale_minutes: int = 10  # "processing" for longer than this = abandoned

    # 20 MB is plenty for contracts. A hard limit protects memory, because uploads
    # are read fully into memory before they are stored.
    max_upload_bytes: int = 20 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    # Cached so the environment is parsed once, not on every request.
    return Settings()
