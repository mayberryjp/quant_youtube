"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ALLIN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(default="", validation_alias=AliasChoices("DATABASE_URL"))
    api_listen_address: str = Field(
        default="0.0.0.0", validation_alias=AliasChoices("API_LISTEN_ADDRESS")
    )
    api_port: int = Field(default=8020, validation_alias=AliasChoices("API_PORT"))

    ingest_wake_time: str = "06:00"
    ingest_interval: int = 86400
    ingest_interval_hours: float = 4
    lookback_days: int = 14
    max_attempts: int = 5
    failed_retry_interval_hours: float = 6.0
    failed_retry_delete_attempts: int = 10

    channel_url: str = "https://www.youtube.com/@allin"
    channel_slug: str = "allin"
    transcript_languages: str = "en,en-US"

    llm_base_url: str = "http://ollama:11434/v1"
    llm_model: str = "llama3.1:8b"
    llm_api_key: str = ""
    llm_timeout: int = 120
    llm_json_mode: bool = True
    llm_num_ctx: int = 8192
    llm_max_tokens: int = 4096
    distill_prompt_version: str = "v1"
    distill_max_chunk_chars: int = 12000

    http_retries: int = 3
    retry_backoff: float = 1.0

    max_page_size: int = 100
    default_page_size: int = 25

    @property
    def transcript_language_preference(self) -> list[str]:
        return [item.strip() for item in self.transcript_languages.split(",") if item.strip()]


settings = Settings()
