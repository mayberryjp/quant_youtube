"""Stage 2 worker: download transcripts for episodes that need one."""

from __future__ import annotations

import argparse
import logging
from datetime import date

from app.config import settings
from app.services.factory import build_transcript_service, run_transcript_once
from app.workers._base import configure_logging, poll_loop

log = logging.getLogger("youtube.worker")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="youtube.workers.transcript")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=900, help="poll interval in seconds")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--restart", default=None, metavar="VIDEO_ID")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=None)
    parser.add_argument("--delete-after-attempts", type=int, default=settings.failed_retry_delete_attempts)
    parser.add_argument("--from-date", type=lambda s: date.fromisoformat(s), default=None)
    parser.add_argument("--to-date", type=lambda s: date.fromisoformat(s), default=None)
    parser.add_argument("-v", "--verbose", action="store_true", help="enable DEBUG logging (per-request detail)")
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    service = build_transcript_service()

    if args.restart:
        log.info("transcript worker: restart %s", args.restart)
        episode = service.episodes.get_by_identifier(args.restart)
        if not episode:
            raise SystemExit(f"Unknown video_id: {args.restart}")
        service.restart(episode)
        return

    if args.retry_failed:
        log.info(
            "transcript worker: retry-failed (max_attempts=%s, delete_after=%s, from=%s, to=%s)",
            args.max_attempts, args.delete_after_attempts, args.from_date, args.to_date,
        )
        service.retry_failed(
            from_date=args.from_date,
            to_date=args.to_date,
            max_attempts=args.max_attempts,
            delete_after_attempts=args.delete_after_attempts,
        )
        return

    if args.once:
        log.info("transcript worker: single pass (limit=%d)", args.limit)
        run_transcript_once(limit=args.limit)
        return

    log.info("transcript worker: polling every %ds (limit=%d)", args.interval, args.limit)
    poll_loop(lambda: run_transcript_once(limit=args.limit), name="transcript", interval=args.interval)


if __name__ == "__main__":
    main()
