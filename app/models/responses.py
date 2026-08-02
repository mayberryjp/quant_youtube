from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EpisodeResponse(BaseModel):
    id: int
    video_id: str
    channel_slug: str | None = None
    title: str | None = None
    published_at: datetime | None = None
    source_url: str
    status: str
    attempts: int = 0
    last_error: str | None = None
    raw_char_count: int | None = None
    summary_char_count: int | None = None
    key_topic_count: int | None = None
    segment_count: int | None = None
    summary: str | None = None


class DistillationResponse(BaseModel):
    id: int
    episode_id: int
    model: str
    prompt_version: str
    summary: str
    key_topics: list[str] = []
    segments: list[dict[str, Any]] = []
    token_usage: dict[str, Any] | None = None
    is_current: bool = True
    created_at: datetime | None = None


class EpisodeDetailResponse(EpisodeResponse):
    raw_text: str | None = None
    distillation: DistillationResponse | None = None


class StatsResponse(BaseModel):
    episodes_discovered: int = 0
    transcripts_fetched: int = 0
    distilled: int = 0
    reprocessed: int = 0
    failures: int = 0
    episodes_total: int = 0
    last_run_date: str | None = None
    last_run_status: str | None = None
    last_heartbeat: str | None = None
