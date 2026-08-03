"""Stage 3: distill fetched transcripts and fan out to entities/watchlist and sentiment."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone

from app.models.domain import Distillation, Episode, EpisodeStatus, WatchlistStatus
from app.services import distiller, entity_pass, sentiment_pass

log = logging.getLogger("quant_allinpodcast.distill")


class DistillService:
    def __init__(
        self,
        *,
        episode_repo,
        distillation_repo,
        llm_client,
        entity_repo=None,
        watchlist_api=None,
        sentiment_client=None,
        model: str,
        distill_prompt_version: str,
        entity_prompt_version: str = "v1",
        sentiment_prompt_version: str = "v1",
        distill_max_chunk_chars: int = 12000,
        max_attempts: int = 5,
        sentiment_enabled: bool = False,
        sentiment_fail_on_error: bool = False,
    ) -> None:
        self.episodes = episode_repo
        self.distillations = distillation_repo
        self.llm = llm_client
        self.entities = entity_repo
        self.watchlist_api = watchlist_api
        self.sentiment = sentiment_client
        self.model = model
        self.distill_pv = distill_prompt_version
        self.entity_pv = entity_prompt_version
        self.sentiment_pv = sentiment_prompt_version
        self.distill_max_chunk_chars = distill_max_chunk_chars
        self.max_attempts = max_attempts
        self.sentiment_enabled = sentiment_enabled
        self.sentiment_fail_on_error = sentiment_fail_on_error

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
        try:
            out, usage = distiller.distill(
                self.llm,
                episode.raw_text or "",
                max_chunk_chars=self.distill_max_chunk_chars,
            )
            self.distillations.upsert(
                Distillation(
                    episode_id=episode.id,
                    model=self.model,
                    prompt_version=self.distill_pv,
                    summary=out.summary,
                    key_topics=out.key_topics,
                    segments=[s.model_dump() for s in out.segments],
                    token_usage=usage or None,
                )
            )
            self._fanout(episode, out, c)
            self.episodes.set_status(episode.id, EpisodeStatus.done)
            self.episodes.touch_stage(episode.id, "distilled")
            c["distilled"] += 1
            log.info("distilled %s", vid)
        except Exception as exc:
            log.exception("distill failed for %s", vid)
            self.episodes.set_status(
                episode.id,
                EpisodeStatus.failed,
                last_error=str(exc)[:500],
                bump_attempts=True,
            )
            c["failures"] += 1
        return c

    def _fanout(self, episode: Episode, out, c: Counter) -> None:
        if self.entities is not None:
            self._deliver_entities(episode, out.summary, c)

        if self.sentiment_enabled and self.sentiment:
            try:
                sent_out, _ = sentiment_pass.extract_sentiment(self.llm, out.summary)
                for obs in sent_out.observations:
                    ok, _sid = self.sentiment.deliver(
                        obs,
                        episode,
                        model=self.model,
                        prompt_version=self.sentiment_pv,
                    )
                    c["sentiments_sent" if ok else "sentiment_failures"] += 1
            except Exception:
                log.exception("sentiment publish failed for %s", episode.video_id)
                c["sentiment_failures"] += 1
                if self.sentiment_fail_on_error:
                    raise

    def _deliver_entities(self, episode: Episode, summary: str, c: Counter) -> None:
        out, _ = entity_pass.extract_entities(self.llm, summary)
        for row in entity_pass.build_rows(
            episode, out, model=self.model, prompt_version=self.entity_pv
        ):
            row_id = self.entities.insert(row)
            if row.ticker and self.watchlist_api is not None:
                status = self.watchlist_api.submit(row, episode)
                submitted_at = (
                    datetime.now(timezone.utc)
                    if status in (WatchlistStatus.submitted, WatchlistStatus.duplicate)
                    else None
                )
                self.entities.set_watchlist(row_id, status, submitted_at=submitted_at)
                if status in (WatchlistStatus.submitted, WatchlistStatus.duplicate):
                    c["entities_submitted"] += 1
                else:
                    c["watchlist_failures"] += 1
            elif not row.ticker:
                self.entities.set_watchlist(row_id, WatchlistStatus.unresolved)

    def reprocess(self, episode: Episode) -> Counter:
        """Re-distill an episode that already has a transcript."""
        self.episodes.reset_for_reprocess(episode.id)
        refreshed = self.episodes.get_by_id(episode.id)
        c = self.distill_one(refreshed)
        c["reprocessed"] += 1
        return c

    def reprocess_candidates(self, **kwargs) -> list[Episode]:
        return self.episodes.reprocess_candidates(**kwargs)
