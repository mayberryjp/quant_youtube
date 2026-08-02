from __future__ import annotations

import logging

from app.models.domain import EpisodeStatus
from app.services.youtube_client import content_hash

log = logging.getLogger("quant_allinpodcast.fetcher")


def discover_new_items(client, episode_repo, run_repo, *, lookback_days: int = 14, channel_targets: list[dict] | None = None) -> int:
    items = client.discover_recent_videos(lookback_days=lookback_days, channels=channel_targets)
    inserted = episode_repo.upsert_discovered(items)
    return inserted


def fetch_transcript(client, episode_repo, episode, *, languages: list[str]) -> bool:
    try:
        text, lang, source = client.fetch_transcript(episode.video_id, languages=languages)
        if not text:
            episode_repo.set_status(
                episode.id,
                EpisodeStatus.failed,
                last_error="transcript unavailable",
                bump_attempts=True,
            )
            return False
        episode_repo.mark_fetched(
            episode.id,
            raw_text=text,
            content_hash=content_hash(text),
            transcript_language=lang,
            transcript_source=source,
        )
        return True
    except Exception as exc:
        log.exception("fetch failed for %s", episode.video_id)
        episode_repo.set_status(
            episode.id,
            EpisodeStatus.failed,
            last_error=str(exc)[:500],
            bump_attempts=True,
        )
        return False
