"""Stage 2 worker: download transcripts for episodes that need one."""

from __future__ import annotations

import argparse
from datetime import date

from app.config import settings
from app.services.factory import build_transcript_service
from app.workers._base import configure_logging, poll_loop


def main(argv: list[str] | None = None) -> None:
    configure_logging()
    parser = argparse.ArgumentParser(prog="quant_allinpodcast.workers.transcript")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=900, help="poll interval in seconds")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--restart", default=None, metavar="VIDEO_ID")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=None)
    parser.add_argument("--delete-after-attempts", type=int, default=settings.failed_retry_delete_attempts)
    parser.add_argument("--from-date", type=lambda s: date.fromisoformat(s), default=None)
    parser.add_argument("--to-date", type=lambda s: date.fromisoformat(s), default=None)
    args = parser.parse_args(argv)

    service = build_transcript_service()

    if args.restart:
        episode = service.episodes.get_by_identifier(args.restart)
        if not episode:
            raise SystemExit(f"Unknown video_id: {args.restart}")
        service.restart(episode)
        return

    if args.retry_failed:
        service.retry_failed(
            from_date=args.from_date,
            to_date=args.to_date,
            max_attempts=args.max_attempts,
            delete_after_attempts=args.delete_after_attempts,
        )
        return

    if args.once:
        service.run(limit=args.limit)
        return

    poll_loop(lambda: build_transcript_service().run(limit=args.limit), name="transcript", interval=args.interval)


if __name__ == "__main__":
    main()
