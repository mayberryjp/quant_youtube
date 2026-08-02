"""Stage 3 worker: distill fetched transcripts into summaries."""

from __future__ import annotations

import argparse
from datetime import date

from app.config import settings
from app.services.factory import build_distill_service
from app.workers._base import configure_logging, poll_loop


def main(argv: list[str] | None = None) -> None:
    configure_logging()
    parser = argparse.ArgumentParser(prog="quant_allinpodcast.workers.distill")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=900, help="poll interval in seconds")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--reprocess", default=None, metavar="VIDEO_ID")
    parser.add_argument("--reprocess-stale", action="store_true")
    parser.add_argument("--from-date", type=lambda s: date.fromisoformat(s), default=None)
    parser.add_argument("--to-date", type=lambda s: date.fromisoformat(s), default=None)
    args = parser.parse_args(argv)

    service = build_distill_service()

    if args.reprocess:
        episode = service.episodes.get_by_identifier(args.reprocess)
        if not episode:
            raise SystemExit(f"Unknown video_id: {args.reprocess}")
        service.reprocess(episode)
        return

    if args.reprocess_stale:
        candidates = service.reprocess_candidates(
            from_date=args.from_date,
            to_date=args.to_date,
            only_stale=True,
            current_model=settings.llm_model,
            current_prompt=settings.distill_prompt_version,
        )
        for episode in candidates:
            service.reprocess(episode)
        return

    if args.once:
        service.run(limit=args.limit)
        return

    poll_loop(lambda: build_distill_service().run(limit=args.limit), name="distill", interval=args.interval)


if __name__ == "__main__":
    main()
