"""Stage 4 worker: collect statuses for submitted distillation jobs."""

from __future__ import annotations

import argparse
import logging

from app.services.factory import run_distill_status_once
from app.workers._base import configure_logging, poll_loop

log = logging.getLogger("youtube.worker")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="youtube.workers.distill_status")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=60, help="poll interval in seconds")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("-v", "--verbose", action="store_true", help="enable DEBUG logging")
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    if args.once:
        log.info("distill status worker: single pass (limit=%d)", args.limit)
        run_distill_status_once(limit=args.limit)
        return

    log.info("distill status worker: polling every %ds (limit=%d)", args.interval, args.limit)
    poll_loop(
        lambda: run_distill_status_once(limit=args.limit),
        name="distill-status",
        interval=args.interval,
    )


if __name__ == "__main__":
    main()
