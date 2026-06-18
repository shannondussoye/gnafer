"""Centralised application configuration.

All environment variables are read once at import time via Pydantic Settings.
Modules should ``from src.config import settings`` instead of calling ``os.getenv()`` directly.
"""

from pathlib import Path

from pydantic_settings import BaseSettings


def _default_psv_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "data" / "Authority_Code_STREET_TYPE_AUT_psv.psv")


class Settings(BaseSettings):
    """Application settings populated from environment variables."""

    # Database
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_name: str = "gnafer"
    db_host: str = "localhost"
    db_port: str = "5432"

    # Worker pool
    trigram_workers: int = 16

    # Ollama / LLM
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:latest"
    llm_verify_threshold: float = 0.8
    llm_batch_size: int = 15

    # Observability
    logtail_token: str = ""

    # Ingestion
    gnaf_csv_path: str = "data/GNAF_CORE.psv"
    street_types_psv: str = ""

    # Job store
    job_ttl_seconds: int = 3600
    job_max_store_size: int = 1000
    max_batch_size: int = 10_000

    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_role_key: str = ""
    supabase_table: str = "addresses"
    supabase_fetch_chunk: int = 500
    supabase_upsert_chunk: int = 100
    supabase_timeout: int = 30
    supabase_batch_size: int = 500
    supabase_read_page_size: int = 1000
    supabase_max_retries: int = 3
    supabase_retry_base_delay_ms: float = 500.0
    supabase_status_pending: str = "pending"
    supabase_status_processing: str = "processing"
    supabase_status_completed: str = "completed"
    supabase_status_failed: str = "failed"

    @property
    def supabase_auth_key(self) -> str:
        """Return the service role key if set, otherwise fall back to the generic key."""
        return self.supabase_service_role_key or self.supabase_key

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def psv_path(self) -> str:
        """Resolved path to the street types authority file."""
        return self.street_types_psv or _default_psv_path()

    @property
    def pool_size(self) -> int:
        """Connection pool size derived from worker count."""
        return self.trigram_workers + 2


settings = Settings()
