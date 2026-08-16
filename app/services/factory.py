"""Builders that wire settings + repositories + clients into the stage services."""

from __future__ import annotations

from datetime import datetime, timezone

from app import db, dependencies as deps
from app.config import settings
from app.models.domain import EpisodeStatus
from app.services.discovery import DiscoveryService
from app.services.distill_api import DistillApiClient
from app.services.distillation import DistillService
from app.services.transcripts import TranscriptService
from app.services.youtube_client import YouTubeClient


def _youtube() -> YouTubeClient:
    return YouTubeClient(
        api_base_url=settings.transcriptapi_base_url,
        api_key=settings.transcriptapi_api_key,
        channel_id=settings.youtube_channel_id,
        channel_handle=settings.youtube_channel_handle,
        channel_slug=settings.channel_slug,
        timeout=settings.transcriptapi_timeout,
        retries=settings.http_retries,
        backoff=settings.retry_backoff,
    )


def _distill_api() -> DistillApiClient:
    return DistillApiClient(
        base_url=settings.distill_api_url,
        submit_timeout=settings.distill_submit_timeout,
        poll_interval=settings.distill_poll_interval,
        job_timeout=settings.distill_job_timeout,
        retries=settings.http_retries,
        backoff=settings.retry_backoff,
    )


def build_discovery_service(engine=None) -> DiscoveryService:
    engine = engine or db.get_engine()
    return DiscoveryService(
        episode_repo=deps.episode_repo(engine),
        run_repo=deps.run_repo(engine),
        youtube_client=_youtube(),
        channel_targets=settings.youtube_channel_targets,
        lookback_days=settings.lookback_days,
    )


def build_transcript_service(engine=None) -> TranscriptService:
    engine = engine or db.get_engine()
    return TranscriptService(
        episode_repo=deps.episode_repo(engine),
        youtube_client=_youtube(),
        transcript_languages=settings.transcript_language_preference,
        max_attempts=settings.max_attempts,
        min_duration_seconds=settings.min_duration_seconds,
    )


def build_distill_service(engine=None) -> DistillService:
    engine = engine or db.get_engine()
    return DistillService(
        episode_repo=deps.episode_repo(engine),
        distillation_repo=deps.distillation_repo(engine),
        distill_api=_distill_api(),
        source=settings.distill_source,
        distill_max_chunk_chars=settings.distill_max_chunk_chars,
        max_attempts=settings.distill_max_attempts,
    )


def run_all_once(run_date=None) -> dict:
    """Run the full chain once (discover -> transcript -> distill). Used by the API trigger."""
    engine = db.get_engine()
    run_date = run_date or datetime.now(timezone.utc).date()
    discovered = build_discovery_service(engine).run(run_date=run_date)
    fetched = build_transcript_service(engine).run()
    distilled = build_distill_service(engine).run()
    result = {"episodes_discovered": discovered, **dict(fetched), **dict(distilled)}
    runs = deps.run_repo(engine)
    runs.add_counters(
        run_date,
        transcripts_fetched=result.get("transcripts_fetched", 0),
        distilled=result.get("distilled", 0),
        reprocessed=result.get("reprocessed", 0),
        failures=result.get("failures", 0),
    )
    status = "partial" if result.get("failures", 0) else "success"
    runs.finish_run(run_date, status, notes=result)
    return result


def requeue_episode(video_id: str, engine=None) -> dict:
    """Full requeue for one episode: reset, re-fetch the transcript, then re-distill."""
    engine = engine or db.get_engine()
    transcripts = build_transcript_service(engine)
    episode = transcripts.episodes.get_by_identifier(video_id)
    if episode is None:
        return {"error": "not_found", "video_id": video_id}
    totals = dict(transcripts.restart(episode))
    refreshed = transcripts.episodes.get_by_id(episode.id)
    if refreshed is not None and refreshed.status == EpisodeStatus.fetched:
        totals.update(dict(build_distill_service(engine).distill_one(refreshed)))
    return totals
