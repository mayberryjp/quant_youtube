"""Builders that wire settings + repositories + clients into the stage services."""

from __future__ import annotations

from app import db, dependencies as deps
from app.config import settings
from app.services.discovery import DiscoveryService
from app.services.distillation import DistillService
from app.services.llm_client import LLMClient
from app.services.sentiment_pass import SentimentApiClient
from app.services.transcripts import TranscriptService
from app.services.watchlist_client import WatchlistClient
from app.services.youtube_client import YouTubeClient


def _youtube() -> YouTubeClient:
    return YouTubeClient(
        api_base_url=settings.youtube_api_base_url,
        api_key=settings.youtube_api_key,
        channel_id=settings.youtube_channel_id,
        channel_handle=settings.youtube_channel_handle,
        channel_slug=settings.channel_slug,
        timeout=settings.llm_timeout,
        retries=settings.http_retries,
        backoff=settings.retry_backoff,
        innertube_web_key=settings.innertube_web_key,
        innertube_android_key=settings.innertube_android_key,
    )


def _watchlist() -> WatchlistClient | None:
    if settings.watchlist_enabled and settings.watchlist_api_url:
        return WatchlistClient(
            api_url=settings.watchlist_api_url,
            api_key=settings.watchlist_api_key,
            source=settings.watchlist_source,
            timeout=settings.watchlist_timeout,
        )
    return None


def _sentiment() -> SentimentApiClient | None:
    if settings.sentiment_enabled and settings.sentiment_api_url:
        return SentimentApiClient(
            url=settings.sentiment_api_url,
            api_key=settings.sentiment_api_key,
            source=settings.sentiment_source,
            timeout=settings.sentiment_timeout,
        )
    return None


def _llm() -> LLMClient:
    return LLMClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout,
        max_tokens=settings.llm_max_tokens,
        json_mode=settings.llm_json_mode,
        num_ctx=settings.llm_num_ctx,
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
    )


def build_distill_service(engine=None) -> DistillService:
    engine = engine or db.get_engine()
    return DistillService(
        episode_repo=deps.episode_repo(engine),
        distillation_repo=deps.distillation_repo(engine),
        llm_client=_llm(),
        watchlist_client=_watchlist(),
        sentiment_client=_sentiment(),
        model=settings.llm_model,
        distill_prompt_version=settings.distill_prompt_version,
        sentiment_prompt_version=settings.sentiment_prompt_version,
        distill_max_chunk_chars=settings.distill_max_chunk_chars,
        max_attempts=settings.max_attempts,
        watchlist_enabled=settings.watchlist_enabled,
        watchlist_fail_on_error=settings.watchlist_fail_on_error,
        sentiment_enabled=settings.sentiment_enabled,
        sentiment_fail_on_error=settings.sentiment_fail_on_error,
    )


def run_all_once(run_date=None) -> dict:
    """Run the full chain once (discover -> transcript -> distill). Used by the API trigger."""
    engine = db.get_engine()
    discovered = build_discovery_service(engine).run(run_date=run_date)
    fetched = build_transcript_service(engine).run()
    distilled = build_distill_service(engine).run()
    return {"episodes_discovered": discovered, **dict(fetched), **dict(distilled)}
