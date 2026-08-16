"""Application settings loaded from environment variables."""

from __future__ import annotations

import re

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = Field(default="", validation_alias=AliasChoices("DATABASE_URL"))
    api_listen_address: str = Field(
        default="0.0.0.0", validation_alias=AliasChoices("API_LISTEN_ADDRESS")
    )
    api_port: int = Field(default=8022, validation_alias=AliasChoices("API_PORT"))

    ingest_wake_time: str = Field(
        default="06:00",
        validation_alias=AliasChoices("INGEST_WAKE_TIME"),
    )
    ingest_interval: int = Field(
        default=86400,
        validation_alias=AliasChoices("INGEST_INTERVAL"),
    )
    ingest_interval_hours: float = Field(
        default=4,
        validation_alias=AliasChoices("INGEST_INTERVAL_HOURS"),
    )
    lookback_days: int = Field(
        default=14,
        validation_alias=AliasChoices("LOOKBACK_DAYS"),
    )
    max_attempts: int = Field(
        default=5,
        validation_alias=AliasChoices("MAX_ATTEMPTS"),
    )
    distill_max_attempts: int = Field(
        default=10,
        validation_alias=AliasChoices("DISTILL_MAX_ATTEMPTS"),
    )
    min_duration_seconds: int = Field(
        default=0,
        validation_alias=AliasChoices("MIN_VIDEO_DURATION_SECONDS", "MIN_DURATION_SECONDS"),
    )
    failed_retry_interval_hours: float = Field(
        default=6.0,
        validation_alias=AliasChoices("FAILED_RETRY_INTERVAL_HOURS"),
    )
    failed_retry_delete_attempts: int = Field(
        default=10,
        validation_alias=AliasChoices("FAILED_RETRY_DELETE_ATTEMPTS"),
    )

    channel_url: str = Field(
        default="https://www.youtube.com/@allin",
        validation_alias=AliasChoices("CHANNEL_URL"),
    )
    channel_slug: str = Field(
        default="allin",
        validation_alias=AliasChoices("CHANNEL_SLUG"),
    )
    youtube_channel_id: str = Field(
        default="",
        validation_alias=AliasChoices("YOUTUBE_CHANNEL_ID"),
    )
    youtube_channel_handle: str = Field(
        default="allin",
        validation_alias=AliasChoices("YOUTUBE_CHANNEL_HANDLE"),
    )
    youtube_channels: str = Field(
        default="allin",
        validation_alias=AliasChoices("YOUTUBE_CHANNELS"),
    )
    transcript_languages: str = Field(
        default="en,asr",
        validation_alias=AliasChoices("TRANSCRIPT_LANGUAGES"),
    )
    # transcriptapi.com backs both discovery (free /channel/latest) and transcript fetching.
    transcriptapi_base_url: str = Field(
        default="https://transcriptapi.com/api/v2",
        validation_alias=AliasChoices("TRANSCRIPTAPI_BASE_URL"),
    )
    transcriptapi_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("TRANSCRIPTAPI_KEY", "TRANSCRIPT_API_KEY"),
    )
    transcriptapi_timeout: int = Field(
        default=120,
        validation_alias=AliasChoices("TRANSCRIPTAPI_TIMEOUT"),
    )

    distill_api_url: str = Field(
        default="http://quant-distill:8021",
        validation_alias=AliasChoices("DISTILL_API_URL"),
    )
    # /v1/process returns 202 immediately, so the submit call only needs a short timeout.
    distill_submit_timeout: int = Field(
        default=30,
        validation_alias=AliasChoices("DISTILL_SUBMIT_TIMEOUT", "DISTILL_API_TIMEOUT"),
    )
    distill_poll_interval: int = Field(
        default=20,
        validation_alias=AliasChoices("DISTILL_POLL_INTERVAL"),
    )
    # A full pipeline run takes 2-30 minutes; give up polling well after that.
    distill_job_timeout: int = Field(
        default=3600,
        validation_alias=AliasChoices("DISTILL_JOB_TIMEOUT"),
    )
    distill_source: str = Field(
        default="youtube",
        validation_alias=AliasChoices("DISTILL_SOURCE"),
    )
    distill_max_chunk_chars: int = Field(
        default=12000,
        validation_alias=AliasChoices("DISTILL_MAX_CHUNK_CHARS"),
    )

    http_retries: int = Field(
        default=3,
        validation_alias=AliasChoices("HTTP_RETRIES"),
    )
    retry_backoff: float = Field(
        default=1.0,
        validation_alias=AliasChoices("RETRY_BACKOFF"),
    )

    max_page_size: int = Field(
        default=100,
        validation_alias=AliasChoices("MAX_PAGE_SIZE"),
    )
    default_page_size: int = Field(
        default=25,
        validation_alias=AliasChoices("DEFAULT_PAGE_SIZE"),
    )

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
