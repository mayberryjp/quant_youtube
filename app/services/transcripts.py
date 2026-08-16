"""Stage 2: download transcripts for episodes that don't have one yet."""

from __future__ import annotations

import logging
from collections import Counter

from app.models.domain import Episode, EpisodeStatus
from app.services.youtube_client import TranscriptRateLimited, content_hash

log = logging.getLogger("youtube.transcripts")


class TranscriptService:
    def __init__(
        self,
        *,
        episode_repo,
        youtube_client,
        transcript_languages: list[str] | None = None,
        max_attempts: int = 5,
        min_duration_seconds: int = 0,
    ) -> None:
        self.episodes = episode_repo
        self.youtube = youtube_client
        self.languages = transcript_languages or ["en-orig", "en", "en-US", "en-GB"]
        self.max_attempts = max_attempts
        self.min_duration_seconds = min_duration_seconds

    def run(self, *, limit: int = 200) -> Counter:
        totals: Counter = Counter()
        pending = self.episodes.list_needing_transcript(limit=limit, max_attempts=self.max_attempts)
        if not pending:
            log.info("transcript pass: no episodes need a transcript (limit=%d, max_attempts=%d)", limit, self.max_attempts)
            return totals
        log.info("transcript pass: %d episode(s) to fetch (limit=%d)", len(pending), limit)
        for i, episode in enumerate(pending, 1):
            log.info("transcript [%d/%d] %s %s", i, len(pending), episode.video_id, (episode.title or "").strip()[:80])
            outcome = self.fetch_one(episode)
            if outcome == "fetched":
                totals["transcripts_fetched"] += 1
            elif outcome == "skipped":
                totals["skipped"] += 1
            else:
                totals["failures"] += 1
        log.info("transcript pass complete: %s", dict(totals))
        return totals

    def fetch_one(self, episode: Episode) -> str:
        try:
            detail = self.youtube.fetch_transcript_detail(episode.video_id, languages=self.languages)
            text = detail.get("text") or ""
            length_seconds = detail.get("length_seconds")
            if (
                self.min_duration_seconds
                and length_seconds is not None
                and length_seconds < self.min_duration_seconds
            ):
                self.episodes.mark_skipped(
                    episode.id,
                    duration_seconds=length_seconds,
                    reason=f"below {self.min_duration_seconds}s minimum ({length_seconds}s)",
                )
                log.info(
                    "skipped %s: %ss < %ss minimum",
                    episode.video_id, length_seconds, self.min_duration_seconds,
                )
                return "skipped"
            if not text:
                self.episodes.set_status(
                    episode.id,
                    EpisodeStatus.failed,
                    last_error="transcript unavailable",
                    bump_attempts=True,
                )
                return "failed"
            self.episodes.mark_fetched(
                episode.id,
                raw_text=text,
                content_hash=content_hash(text),
                transcript_language=detail.get("language"),
                transcript_source=detail.get("source"),
                duration_seconds=length_seconds,
            )
            if length_seconds:
                log.info("fetched transcript for %s (%ds)", episode.video_id, length_seconds)
            else:
                log.info("fetched transcript for %s", episode.video_id)
            return "fetched"
        except TranscriptRateLimited as exc:
            # Transient throttling: keep the episode retryable instead of permanently failing it.
            log.warning("rate limited fetching %s; leaving retryable", episode.video_id)
            self.episodes.set_status(
                episode.id,
                EpisodeStatus.discovered,
                last_error=str(exc)[:500],
                bump_attempts=False,
            )
            return "failed"
        except Exception as exc:
            log.exception("fetch failed for %s", episode.video_id)
            self.episodes.set_status(
                episode.id,
                EpisodeStatus.failed,
                last_error=str(exc)[:500],
                bump_attempts=True,
            )
            return "failed"

    def restart(self, episode: Episode) -> Counter:
        """Wipe the transcript and re-fetch from scratch."""
        self.episodes.reset_full(episode.id)
        refreshed = self.episodes.get_by_id(episode.id)
        totals: Counter = Counter({"reprocessed": 1})
        outcome = self.fetch_one(refreshed)
        if outcome == "fetched":
            totals["transcripts_fetched"] += 1
        elif outcome == "skipped":
            totals["skipped"] += 1
        else:
            totals["failures"] += 1
        return totals

    def retry_failed(
        self,
        *,
        from_date=None,
        to_date=None,
        max_attempts: int | None = None,
        delete_after_attempts: int | None = None,
    ) -> Counter:
        candidates = self.episodes.failed_candidates(
            from_date=from_date,
            to_date=to_date,
            max_attempts=max_attempts,
        )
        totals: Counter = Counter()
        for episode in candidates:
            if delete_after_attempts is not None and episode.attempts >= delete_after_attempts:
                if self.episodes.delete(episode.id):
                    totals["deleted"] += 1
                continue
            totals["retried"] += 1
            totals.update(self.restart(episode))
            refreshed = self.episodes.get_by_id(episode.id)
            if (
                delete_after_attempts is not None
                and refreshed is not None
                and refreshed.status == EpisodeStatus.failed
                and refreshed.attempts >= delete_after_attempts
            ):
                if self.episodes.delete(refreshed.id):
                    totals["deleted"] += 1
        return totals
