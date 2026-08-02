"""Stage 1: crawl YouTube channels for new episodes and log the daily run."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

log = logging.getLogger("quant_allinpodcast.discovery")


class DiscoveryService:
    def __init__(
        self,
        *,
        episode_repo,
        run_repo,
        youtube_client,
        channel_targets: list[dict[str, str]] | None = None,
        lookback_days: int = 14,
    ) -> None:
        self.episodes = episode_repo
        self.runs = run_repo
        self.youtube = youtube_client
        self.channel_targets = channel_targets or []
        self.lookback_days = lookback_days

    def run(
        self,
        run_date: date | None = None,
        *,
        lookback_days: int | None = None,
        max_items: int = 80,
    ) -> int:
        run_date = run_date or datetime.now(timezone.utc).date()
        self.runs.start_run(run_date)
        try:
            items = self.youtube.discover_recent_videos(
                lookback_days=lookback_days if lookback_days is not None else self.lookback_days,
                max_items=max_items,
                channels=self.channel_targets,
            )
            new_count = self.episodes.upsert_discovered(items)
            self.runs.add_counters(run_date, episodes_discovered=new_count)
            self.runs.finish_run(run_date, "success", notes={"crawled": len(items), "new": new_count})
            log.info("discovery crawled %d videos, %d new", len(items), new_count)
            return new_count
        except Exception as exc:
            log.exception("discovery run failed")
            self.runs.add_counters(run_date, failures=1)
            self.runs.finish_run(run_date, "failed", notes={"error": str(exc)[:500]})
            raise
