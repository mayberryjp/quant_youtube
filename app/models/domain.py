from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class EpisodeStatus(str, Enum):
    discovered = "discovered"
    fetched = "fetched"
    distilled = "distilled"
    done = "done"
    failed = "failed"


class Episode(BaseModel):
    id: int | None = None
    video_id: str
    channel_slug: str = "allin"
    title: str | None = None
    published_at: datetime | None = None
    source_url: str
    thumbnail_url: str | None = None
    description: str | None = None
    duration_seconds: int | None = None
    transcript_language: str | None = None
    transcript_source: str | None = None
    content_hash: str | None = None
    raw_text: str | None = None
    status: EpisodeStatus = EpisodeStatus.discovered
    attempts: int = 0
    last_error: str | None = None
    discovered_at: datetime | None = None
    fetched_at: datetime | None = None
    distilled_at: datetime | None = None

    raw_char_count: int | None = None
    summary_char_count: int | None = None
    key_topic_count: int | None = None
    segment_count: int | None = None


class Distillation(BaseModel):
    id: int | None = None
    episode_id: int
    model: str
    prompt_version: str
    summary: str
    key_topics: list[str] = Field(default_factory=list)
    segments: list[dict] = Field(default_factory=list)
    token_usage: dict | None = None
    is_current: bool = True
    created_at: datetime | None = None


class IngestRun(BaseModel):
    run_date: date
    status: str = "success"
    episodes_discovered: int = 0
    transcripts_fetched: int = 0
    distilled: int = 0
    reprocessed: int = 0
    failures: int = 0
    last_heartbeat: datetime | None = None
    notes: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
