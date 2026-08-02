"""Stage 1 worker: crawl channels daily and insert new episode rows."""

from __future__ import annotations

import argparse
from datetime import date

from app.config import settings
from app.services.factory import build_discovery_service
from app.workers._base import configure_logging, daily_loop


def main(argv: list[str] | None = None) -> None:
    configure_logging()
    parser = argparse.ArgumentParser(prog="quant_allinpodcast.workers.discover")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--wake-time", default=settings.ingest_wake_time)
    parser.add_argument("--interval-hours", type=float, default=0.0)
    parser.add_argument("--date", type=lambda s: date.fromisoformat(s), default=None)
    parser.add_argument("--lookback-days", type=int, default=None)
    parser.add_argument("--max-items", type=int, default=80)
    args = parser.parse_args(argv)

    def _run() -> None:
        build_discovery_service().run(
            run_date=args.date,
            lookback_days=args.lookback_days,
            max_items=args.max_items,
        )

    if args.once:
        _run()
        return

    daily_loop(_run, name="discover", wake_time=args.wake_time, interval_hours=args.interval_hours)


if __name__ == "__main__":
    main()
