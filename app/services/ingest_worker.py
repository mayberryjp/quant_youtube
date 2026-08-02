from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta

from app import db, dependencies as deps
from app.config import settings
from app.services.llm_client import LLMClient
from app.services.pipeline import Pipeline
from app.services.youtube_client import YouTubeClient

log = logging.getLogger("quant_allinpodcast.worker")


def build_pipeline(engine=None) -> Pipeline:
    engine = engine or db.get_engine()
    return Pipeline(
        episode_repo=deps.episode_repo(engine),
        distillation_repo=deps.distillation_repo(engine),
        run_repo=deps.run_repo(engine),
        youtube_client=YouTubeClient(
            channel_url=settings.channel_url,
            timeout=settings.llm_timeout,
            retries=settings.http_retries,
            backoff=settings.retry_backoff,
        ),
        llm_client=LLMClient(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout,
            max_tokens=settings.llm_max_tokens,
            json_mode=settings.llm_json_mode,
            num_ctx=settings.llm_num_ctx,
        ),
        model=settings.llm_model,
        distill_prompt_version=settings.distill_prompt_version,
        lookback_days=settings.lookback_days,
        max_attempts=settings.max_attempts,
        distill_max_chunk_chars=settings.distill_max_chunk_chars,
        transcript_languages=settings.transcript_language_preference,
    )


def seconds_until_wake(wake_time: str, now: datetime | None = None) -> float:
    now = now or datetime.now()
    hh, mm = [int(x) for x in wake_time.split(":", 1)]
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def run_worker(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )
    parser = argparse.ArgumentParser(prog="quant_allinpodcast.ingest_worker")
    parser.add_argument("--wake-time", default=settings.ingest_wake_time)
    parser.add_argument("--interval", type=int, default=settings.ingest_interval)
    parser.add_argument("--interval-hours", type=float, default=settings.ingest_interval_hours)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--date", type=lambda s: date.fromisoformat(s), default=None)
    parser.add_argument("--reprocess", default=None, metavar="VIDEO_ID")
    parser.add_argument("--restart", default=None, metavar="VIDEO_ID")
    parser.add_argument("--reprocess-stale", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=None)
    parser.add_argument("--delete-after-attempts", type=int, default=settings.failed_retry_delete_attempts)
    parser.add_argument("--from-date", type=lambda s: date.fromisoformat(s), default=None)
    parser.add_argument("--to-date", type=lambda s: date.fromisoformat(s), default=None)
    args = parser.parse_args(argv)

    p = build_pipeline()

    if args.reprocess:
        ep = p.episodes.get_by_identifier(args.reprocess)
        if not ep:
            raise SystemExit(f"Unknown video_id: {args.reprocess}")
        p.reprocess(ep)
        return

    if args.restart:
        ep = p.episodes.get_by_identifier(args.restart)
        if not ep:
            raise SystemExit(f"Unknown video_id: {args.restart}")
        p.restart(ep)
        return

    if args.reprocess_stale:
        candidates = p.episodes.reprocess_candidates(
            from_date=args.from_date,
            to_date=args.to_date,
            only_stale=True,
            current_model=settings.llm_model,
            current_prompt=settings.distill_prompt_version,
        )
        for ep in candidates:
            p.reprocess(ep)
        return

    if args.retry_failed:
        p.retry_failed(
            from_date=args.from_date,
            to_date=args.to_date,
            max_attempts=args.max_attempts,
            delete_after_attempts=args.delete_after_attempts,
        )
        return

    if args.once:
        p.run(run_date=args.date)
        return

    while True:
        if args.interval_hours > 0:
            p.run()
            sleep_for = max(60, int(args.interval_hours * 3600))
        else:
            sleep_for = int(seconds_until_wake(args.wake_time))
            log.info("sleeping %.1f seconds until %s", sleep_for, args.wake_time)
            time.sleep(sleep_for)
            p.run()
            sleep_for = args.interval
        log.info("sleeping %s seconds", sleep_for)
        time.sleep(sleep_for)


if __name__ == "__main__":
    run_worker()
