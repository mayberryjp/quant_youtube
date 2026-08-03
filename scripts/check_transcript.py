#!/usr/bin/env python3
"""Fetch a YouTube transcript using the app's own env-driven config, with verbose logs.

Committable (not a pytest). Runs the exact YouTubeClient the workers use, so it doubles
as a diagnostic for the "transcript unavailable" case: it logs the effective config,
how many caption clients/tracks were found, the available languages, and a preview of
the text.

Run inside the container (env comes from .env):
    docker compose exec app python scripts/check_transcript.py
    docker compose exec app python scripts/check_transcript.py VIDEO_ID_OR_URL -v

Exit codes: 0 ok | 2 no keys | 3 rate limited | 4 unavailable | 5 unexpected error
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `app` importable when run by path

from app.config import settings
from app.services.factory import _youtube
from app.services.youtube_client import TranscriptRateLimited

log = logging.getLogger("check_transcript")


def _mask(key: str) -> str:
    return f"set (…{key[-4:]})" if key else "NOT SET"


def _extract_id(value: str) -> str:
    match = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", value)
    return match.group(1) if match else value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch a YouTube transcript via the app's env-driven client.")
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

    video_id = _extract_id(args.video)
    log.info("video id              : %s", video_id)
    log.info("innertube web key     : %s", _mask(settings.innertube_web_key))
    log.info("innertube android key : %s", _mask(settings.innertube_android_key))
    log.info("language preference   : %s", settings.transcript_language_preference)
    log.info("api base / timeout    : %s / %ss  retries=%s", settings.youtube_api_base_url, settings.llm_timeout, settings.http_retries)

    if not (settings.innertube_web_key or settings.innertube_android_key):
        log.error(
            "No InnerTube keys configured -> zero caption clients -> fetch cannot work. "
            "Set INNERTUBE_WEB_KEY / INNERTUBE_ANDROID_KEY in your .env and retry."
        )
        return 2

    client = _youtube()
    log.info("caption clients built  : %d", len(client._innertube_clients))

    # Diagnostic pass: list tracks before the real fetch so empty results are obvious in the logs.
    t0 = time.perf_counter()
    tracks, rate_limited = client._list_caption_tracks(video_id)
    log.info("caption tracks returned: %d (rate_limited=%s) in %.2fs", len(tracks), rate_limited, time.perf_counter() - t0)
    if tracks:
        log.info("available languages    : %s", [t.get("languageCode") for t in tracks])
    else:
        log.warning(
            "InnerTube returned NO caption tracks. Most likely datacenter-IP gating or captions "
            "disabled for this video (yt-dlp from a residential IP may still succeed)."
        )

    try:
        t0 = time.perf_counter()
        text, lang, source = client.fetch_transcript(video_id, languages=settings.transcript_language_preference)
    except TranscriptRateLimited as exc:
        log.error("rate limited (HTTP 429): %s", exc)
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
