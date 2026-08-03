#!/usr/bin/env python3
"""Fetch a YouTube transcript through the app's transcriptapi.com client, with verbose logs.

Committable (not a pytest). Uses the exact YouTubeClient the workers use, so it doubles
as a diagnostic for the "transcript unavailable" case: it logs the effective config, the
languages transcriptapi.com reports for the video (free /youtube/info lookup), and a
preview of the fetched text.

Run inside the container (env comes from .env):
    docker compose exec app python scripts/check_transcript.py
    docker compose exec app python scripts/check_transcript.py VIDEO_ID_OR_URL -v

Exit codes: 0 ok | 2 no api key | 3 transient (rate limit / credits / 5xx) | 4 unavailable | 5 unexpected error
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `app` importable when run by path

from app.config import settings
from app.services.factory import _youtube
from app.services.youtube_client import TranscriptRateLimited


def _mask(key: str) -> str:
    return f"set (…{key[-4:]})" if key else "NOT SET"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch a YouTube transcript via the app's transcriptapi.com client.")
    parser.add_argument(
        "video",
        nargs="?",
        default=os.getenv("LIVE_TRANSCRIPT_VIDEO_ID", "sBI3_gPf13s"),
        help="YouTube video id or URL (defaults to LIVE_TRANSCRIPT_VIDEO_ID or a sample)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="enable debug logging")
    parser.add_argument("--preview", type=int, default=800, help="characters of transcript to print")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    log = logging.getLogger("check_transcript")

    log.info("video                 : %s", args.video)
    log.info("transcriptapi key     : %s", _mask(settings.transcriptapi_api_key))
    log.info("transcriptapi base    : %s", settings.transcriptapi_base_url)
    log.info("language preference   : %s", settings.transcript_language_preference)
    log.info("timeout / retries     : %ss / %s", settings.llm_timeout, settings.http_retries)

    if not settings.transcriptapi_api_key:
        log.error(
            "No TRANSCRIPTAPI_KEY configured -> transcriptapi.com calls cannot authenticate. "
            "Set TRANSCRIPTAPI_KEY in your .env and retry (key: https://transcriptapi.com/dashboard/api-keys)."
        )
        return 2

    client = _youtube()

    # Free /youtube/info pass: surface the languages the video offers before spending a credit.
    try:
        langs = client.available_languages(args.video)
        if langs:
            log.info("available languages    : %s", [f"{l.get('code')} ({l.get('name')})" for l in langs])
        else:
            log.warning("no available languages reported (video may not exist or have no captions)")
    except TranscriptRateLimited as exc:
        log.warning("info lookup throttled  : %s", exc)
    except Exception:
        log.warning("info lookup failed", exc_info=True)

    try:
        t0 = time.perf_counter()
        text, lang, source = client.fetch_transcript(args.video, languages=settings.transcript_language_preference)
    except TranscriptRateLimited as exc:
        log.error("transient failure (rate limit / credits / 5xx): %s", exc)
        return 3
    except ValueError as exc:
        log.error("transcript unavailable: %s", exc)
        return 4
    except Exception:
        log.exception("unexpected error fetching transcript")
        return 5

    elapsed = time.perf_counter() - t0
    log.info("SUCCESS: %d chars  language=%s  source=%s  in %.2fs", len(text), lang, source, elapsed)
    print("-" * 70)
    print(text[: args.preview] + ("…" if len(text) > args.preview else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
