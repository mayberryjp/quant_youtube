from __future__ import annotations

import logging
from collections import Counter
from datetime import date, datetime, timezone

from app.models.domain import Distillation, Episode, EpisodeStatus
from app.services import distiller
from app.services.transcript_fetcher import discover_new_items, fetch_transcript

log = logging.getLogger("quant_allinpodcast.pipeline")


class Pipeline:
    def __init__(
        self,
        *,
        episode_repo,
        distillation_repo,
        run_repo,
        youtube_client,
        llm_client,
        model: str,
        distill_prompt_version: str,
        lookback_days: int = 14,
        max_attempts: int = 5,
        distill_max_chunk_chars: int = 12000,
        transcript_languages: list[str] | None = None,
    ) -> None:
        self.episodes = episode_repo
        self.distillations = distillation_repo
        self.runs = run_repo
        self.youtube = youtube_client
        self.llm = llm_client
        self.model = model
        self.distill_pv = distill_prompt_version
        self.lookback_days = lookback_days
        self.max_attempts = max_attempts
        self.distill_max_chunk_chars = distill_max_chunk_chars
        self.transcript_languages = transcript_languages or ["en", "en-US"]

    def discover(self) -> int:
        return discover_new_items(self.youtube, self.episodes, self.runs, lookback_days=self.lookback_days)

    def process_one(self, episode: Episode) -> Counter:
        c: Counter = Counter()
        vid = episode.video_id
        try:
            status = episode.status
            if status == EpisodeStatus.discovered:
                if not fetch_transcript(
                    self.youtube,
                    self.episodes,
                    episode,
                    languages=self.transcript_languages,
                ):
                    c["failures"] += 1
                    return c
                episode = self.episodes.get_by_id(episode.id)
                status = EpisodeStatus.fetched
                c["transcripts_fetched"] += 1

            if status == EpisodeStatus.fetched:
                raw = episode.raw_text or ""
                out, usage = distiller.distill(
                    self.llm,
                    raw,
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
                self.episodes.set_status(episode.id, EpisodeStatus.done)
                self.episodes.touch_stage(episode.id, "distilled")
                c["distilled"] += 1
                log.info("processed %s done", vid)
            return c
        except Exception as exc:
            log.exception("processing failed for %s", vid)
            self.episodes.set_status(
                episode.id,
                EpisodeStatus.failed,
                last_error=str(exc)[:500],
                bump_attempts=True,
            )
            c["failures"] += 1
            return c

    def run(self, run_date: date | None = None, *, limit: int = 200) -> Counter:
        run_date = run_date or datetime.now(timezone.utc).date()
        self.runs.start_run(run_date)
        totals: Counter = Counter()
        try:
            discovered = self.discover()
            if discovered:
                self.runs.add_counters(run_date, episodes_discovered=discovered)
                totals["episodes_discovered"] += discovered

            actionable = self.episodes.list_actionable(
                limit=limit,
                max_attempts=self.max_attempts,
                include_failed=False,
            )
            for ep in actionable:
                c = self.process_one(ep)
                totals.update(c)
                self.runs.add_counters(run_date, **c)
            status = "partial" if totals.get("failures") else "success"
        except Exception:
            log.exception("run failed")
            status = "failed"
            totals["failures"] += 1
            self.runs.add_counters(run_date, failures=1)
        self.runs.finish_run(run_date, status, notes={"totals": dict(totals)})
        return totals

    def reprocess(self, episode: Episode, run_date: date | None = None) -> Counter:
        self.episodes.reset_for_reprocess(episode.id)
        refreshed = self.episodes.get_by_id(episode.id)
        c = self.process_one(refreshed)
        c["reprocessed"] += 1
        if run_date is not None:
            self.runs.add_counters(run_date, **c)
        return c

    def restart(self, episode: Episode, run_date: date | None = None) -> Counter:
        self.episodes.reset_full(episode.id)
        refreshed = self.episodes.get_by_id(episode.id)
        c = self.process_one(refreshed)
        c["reprocessed"] += 1
        if run_date is not None:
            self.runs.add_counters(run_date, **c)
        return c

    def retry_failed(
        self,
        *,
        from_date=None,
        to_date=None,
        max_attempts: int | None = None,
        delete_after_attempts: int | None = None,
        run_date: date | None = None,
    ) -> Counter:
        candidates = self.episodes.failed_candidates(
            from_date=from_date,
            to_date=to_date,
            max_attempts=max_attempts,
        )
        totals: Counter = Counter()
        retried = 0
        for ep in candidates:
            if delete_after_attempts is not None and ep.attempts >= delete_after_attempts:
                if self.episodes.delete(ep.id):
                    totals["deleted"] += 1
                continue
            retried += 1
            totals.update(self.restart(ep, run_date=run_date))
            refreshed = self.episodes.get_by_id(ep.id)
            if (
                delete_after_attempts is not None
                and refreshed is not None
                and refreshed.status == EpisodeStatus.failed
                and refreshed.attempts >= delete_after_attempts
            ):
                if self.episodes.delete(refreshed.id):
                    totals["deleted"] += 1
        totals["retried"] = retried
        return totals
