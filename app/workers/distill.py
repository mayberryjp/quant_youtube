"""Stage 3 worker: distill fetched transcripts into summaries."""

from __future__ import annotations

import argparse
import logging
from datetime import date

from app.services.factory import build_distill_service
from app.workers._base import configure_logging, poll_loop

log = logging.getLogger("youtube.worker")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="youtube.workers.distill")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=900, help="poll interval in seconds")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--reprocess", default=None, metavar="VIDEO_ID")
    parser.add_argument("--from-date", type=lambda s: date.fromisoformat(s), default=None)
    parser.add_argument("--to-date", type=lambda s: date.fromisoformat(s), default=None)
    parser.add_argument("-v", "--verbose", action="store_true", help="enable DEBUG logging")
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    service = build_distill_service()

    if args.reprocess:
        log.info("distill worker: reprocess %s", args.reprocess)
        episode = service.episodes.get_by_identifier(args.reprocess)
        if not episode:
            raise SystemExit(f"Unknown video_id: {args.reprocess}")
        service.reprocess(episode)
        return

    if args.once:
        log.info("distill worker: single pass (limit=%d)", args.limit)
        service.run(limit=args.limit)
        return

    log.info("distill worker: polling every %ds (limit=%d)", args.interval, args.limit)
    poll_loop(lambda: build_distill_service().run(limit=args.limit), name="distill", interval=args.interval)


if __name__ == "__main__":
    main()
