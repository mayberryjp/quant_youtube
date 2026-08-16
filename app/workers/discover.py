"""Stage 1 worker: crawl channels daily and insert new episode rows."""

from __future__ import annotations

import argparse
import logging
from datetime import date

from app.config import settings
from app.services.factory import build_discovery_service
from app.workers._base import configure_logging, daily_loop

log = logging.getLogger("youtube.worker")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="youtube.workers.discover")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--wake-time", default=settings.ingest_wake_time)
    parser.add_argument("--interval-hours", type=float, default=0.0)
    parser.add_argument("--date", type=lambda s: date.fromisoformat(s), default=None)
    parser.add_argument("--lookback-days", type=int, default=None)
    parser.add_argument("--max-items", type=int, default=80)
    parser.add_argument("-v", "--verbose", action="store_true", help="enable DEBUG logging (per-request detail)")
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    def _run() -> None:
        build_discovery_service().run(
            run_date=args.date,
            lookback_days=args.lookback_days,
            max_items=args.max_items,
        )

    if args.once:
        log.info("discover worker: single pass (lookback_days=%s, max_items=%d)", args.lookback_days, args.max_items)
        _run()
        return

    log.info("discover worker: daily loop (wake=%s, interval_hours=%s)", args.wake_time, args.interval_hours)
    daily_loop(_run, name="discover", wake_time=args.wake_time, interval_hours=args.interval_hours)


if __name__ == "__main__":
    main()
