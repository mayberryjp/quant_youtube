"""Application settings loaded from environment variables."""

from __future__ import annotations

import re

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
    youtube_api_base_url: str = "https://www.googleapis.com"
    youtube_api_key: str = ""
    youtube_channel_id: str = ""
    youtube_channel_handle: str = "allin"
    youtube_channels: str = "allin"
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

    watchlist_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("ALLIN_WATCHLIST_ENABLED", "WATCHLIST_ENABLED"),
    )
    watchlist_api_url: str = Field(
        default="",
        validation_alias=AliasChoices("ALLIN_WATCHLIST_API_URL", "WATCHLIST_API_URL"),
    )
    watchlist_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ALLIN_WATCHLIST_API_KEY", "WATCHLIST_API_KEY"),
    )
    watchlist_timeout: int = Field(
        default=15,
        validation_alias=AliasChoices("ALLIN_WATCHLIST_TIMEOUT", "WATCHLIST_TIMEOUT"),
    )
    watchlist_source: str = Field(
        default="quant_allinpodcast",
        validation_alias=AliasChoices("ALLIN_WATCHLIST_SOURCE", "WATCHLIST_SOURCE"),
    )
    watchlist_fail_on_error: bool = Field(
        default=False,
        validation_alias=AliasChoices("ALLIN_WATCHLIST_FAIL_ON_ERROR", "WATCHLIST_FAIL_ON_ERROR"),
    )

    http_retries: int = 3
    retry_backoff: float = 1.0

    max_page_size: int = 100
    default_page_size: int = 25

    @property
    def transcript_language_preference(self) -> list[str]:
        return [item.strip() for item in self.transcript_languages.split(",") if item.strip()]

    @property
    def youtube_channel_targets(self) -> list[dict[str, str]]:
        targets: list[dict[str, str]] = []

        for token in [t.strip() for t in self.youtube_channels.split(",") if t.strip()]:
            slug: str | None = None
            spec = token
            if "=" in token:
                slug, spec = [x.strip() for x in token.split("=", 1)]

            if spec.lower().startswith("id:"):
                channel_id = spec[3:].strip()
                if not channel_id:
                    continue
                entry_slug = slug or _slugify(channel_id)
                targets.append({"channel_id": channel_id, "channel_handle": "", "channel_slug": entry_slug})
            else:
                handle = spec.lstrip("@").strip()
                if not handle:
                    continue
                entry_slug = slug or _slugify(handle)
                targets.append({"channel_id": "", "channel_handle": handle, "channel_slug": entry_slug})

        if targets:
            return targets

        if self.youtube_channel_id:
            return [{
                "channel_id": self.youtube_channel_id,
                "channel_handle": "",
                "channel_slug": self.channel_slug,
            }]

        return [{
            "channel_id": "",
            "channel_handle": self.youtube_channel_handle,
            "channel_slug": self.channel_slug,
        }]


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "channel"


settings = Settings()
