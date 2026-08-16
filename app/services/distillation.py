"""Stage 3: submit fetched transcripts to the shared distillation API."""

from __future__ import annotations

import logging
from collections import Counter

from app.models.domain import Distillation, Episode, EpisodeStatus
from app.services.distill_api import DistillJobTimeout

log = logging.getLogger("youtube.distill")


class DistillService:
    def __init__(
        self,
        *,
        episode_repo,
        distillation_repo,
        distill_api,
        source: str = "youtube",
        distill_max_chunk_chars: int = 12000,
        max_attempts: int = 10,
    ) -> None:
        self.episodes = episode_repo
        self.distillations = distillation_repo
        self.distill_api = distill_api
        self.source = source
        self.distill_max_chunk_chars = distill_max_chunk_chars
        self.max_attempts = max_attempts

    def run(self, *, limit: int = 200) -> Counter:
        totals: Counter = Counter()
        pending = self.episodes.list_needing_distill(limit=limit, max_attempts=self.max_attempts)
        if not pending:
            log.info("distill pass: no episodes need distillation (limit=%d, max_attempts=%d)", limit, self.max_attempts)
            return totals
        log.info("distill pass: %d episode(s) to distill (limit=%d)", len(pending), limit)
        for i, episode in enumerate(pending, 1):
            log.info("distill [%d/%d] %s %s", i, len(pending), episode.video_id, (episode.title or "").strip()[:80])
            totals.update(self.distill_one(episode))
        log.info("distill pass complete: %s", dict(totals))
        return totals

    def distill_one(self, episode: Episode) -> Counter:
        c: Counter = Counter()
        vid = episode.video_id
        payload = self._build_payload(episode)
        try:
            job_id = episode.distill_job_id
            if job_id:
                log.info("resuming distill job %s for %s", job_id, vid)
            else:
                job_id = self.distill_api.submit(payload)
                self.episodes.set_distill_job(episode.id, job_id)
                log.info("submitted distill job %s for %s", job_id, vid)
            response = self.distill_api.wait_for_result(job_id)
        except DistillJobTimeout as exc:
            # The job is still running server-side; the stored job_id resumes polling next pass.
            log.warning("distill still pending for %s: %s", vid, exc)
            c["pending"] += 1
            return c
        except Exception as exc:
            log.exception("distill failed for %s", vid)
            self._mark_failed(episode, exc)
            c["failures"] += 1
            return c

        try:
            artifact = response["distillation"]
            processing = response.get("processing") or {}
            self.distillations.upsert(
                Distillation(
                    episode_id=episode.id,
                    model=processing.get("model") or "unknown",
                    prompt_version=processing.get("distill_prompt_version") or "unknown",
                    summary=artifact.get("summary") or "",
                    key_topics=artifact.get("key_topics") or [],
                    segments=artifact.get("segments") or [],
                    token_usage=processing.get("token_usage"),
                    request_payload=payload,
                    response_payload=response,
                    request_id=response.get("request_id"),
                )
            )
            self.episodes.set_distill_job(episode.id, None)
            self.episodes.set_status(episode.id, EpisodeStatus.done)
            self.episodes.touch_stage(episode.id, "distilled")
            c["distilled"] += 1
            log.info("distilled %s", vid)
        except Exception as exc:
            log.exception("storing distillation failed for %s", vid)
            self._mark_failed(episode, exc)
            c["failures"] += 1
        return c

    def _mark_failed(self, episode: Episode, exc: Exception) -> None:
        attempts = episode.distill_attempts + 1
        self.episodes.set_distill_job(episode.id, None)
        self.episodes.bump_distill_attempts(episode.id)
        self.episodes.set_status(
            episode.id,
            EpisodeStatus.failed,
            last_error=str(exc)[:500],
        )
        if attempts >= self.max_attempts:
            log.error(
                "distill giving up on %s after %d attempt(s)", episode.video_id, attempts
            )
        else:
            log.info(
                "distill attempt %d/%d failed for %s; will retry",
                attempts,
                self.max_attempts,
                episode.video_id,
            )

    def _build_payload(self, episode: Episode) -> dict:
        payload = {
            "source": self.source,
            "source_type": "youtube",
            "source_item_id": episode.video_id,
            "title": episode.title,
            "text": episode.raw_text or "",
            "metadata": {
                "url": episode.source_url,
                "channel": episode.channel_slug,
                "thumbnail_url": episode.thumbnail_url,
                "description": episode.description,
                "transcript_language": episode.transcript_language,
                "transcript_source": episode.transcript_source,
            },
            "options": {
                "include_sentiment": True,
                "include_entities": True,
                "include_watchlist": True,
                "watchlist_required": False,
                "max_chunk_chars": self.distill_max_chunk_chars,
            },
        }
        if episode.published_at is not None:
            payload["observed_at"] = episode.published_at.isoformat()
        return payload

    def reprocess(self, episode: Episode) -> Counter:
        """Re-distill an episode that already has a transcript."""
        self.episodes.reset_for_reprocess(episode.id)
        refreshed = self.episodes.get_by_id(episode.id)
        c = self.distill_one(refreshed)
        c["reprocessed"] += 1
        return c

    def reprocess_candidates(self, **kwargs) -> list[Episode]:
        return self.episodes.reprocess_candidates(**kwargs)
