"""Shared loop/logging helpers for the stage workers."""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timedelta

log = logging.getLogger("youtube.worker")


def configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )


def seconds_until_wake(wake_time: str, now: datetime | None = None) -> float:
    now = now or datetime.now()
    hh, mm = [int(x) for x in wake_time.split(":", 1)]
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def daily_loop(run_once, *, name: str, wake_time: str, interval_hours: float = 0.0) -> None:
    """Run once per day at wake_time, or every interval_hours if > 0."""
    while True:
        try:
            if interval_hours > 0:
                run_once()
                sleep_for = max(60, int(interval_hours * 3600))
                log.info("%s sleeping %ds", name, sleep_for)
                time.sleep(sleep_for)
            else:
                sleep_for = int(seconds_until_wake(wake_time))
                log.info("%s sleeping %ds until %s", name, sleep_for, wake_time)
                time.sleep(sleep_for)
                run_once()
        except Exception:
            log.exception("%s loop failed; retrying in 10s", name)
            time.sleep(10)


def poll_loop(run_once, *, name: str, interval: int) -> None:
    """Process the backlog, then sleep interval seconds, forever."""
    while True:
        try:
            run_once()
        except Exception:
            log.exception("%s loop failed", name)
        sleep_for = max(5, interval)
        time.sleep(sleep_for)
