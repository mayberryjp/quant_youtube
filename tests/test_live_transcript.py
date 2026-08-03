"""Env-driven live transcript smoke test.

Committed to git, but only runs where the InnerTube keys are configured (i.e. inside
the container with a populated .env). It is skipped automatically in offline/unit
contexts so the normal `pytest -q` run stays green.

Configuration (all read from the environment via app.config.settings):
- INNERTUBE_WEB_KEY / INNERTUBE_ANDROID_KEY  -> required, gates the test
- TRANSCRIPT_LANGUAGES                        -> language preference order
- LIVE_TRANSCRIPT_VIDEO_ID                    -> optional override of the sample video
"""

from __future__ import annotations

import os

import pytest

from app.config import settings
from app.services.factory import _youtube
from app.services.youtube_client import TranscriptRateLimited

_HAS_KEYS = bool(settings.innertube_web_key or settings.innertube_android_key)
_VIDEO_ID = os.getenv("LIVE_TRANSCRIPT_VIDEO_ID", "sBI3_gPf13s")


@pytest.mark.skipif(
    not _HAS_KEYS,
    reason="InnerTube keys not set; configure INNERTUBE_WEB_KEY/INNERTUBE_ANDROID_KEY to run this live test",
)
def test_live_transcript_is_human_readable():
    client = _youtube()
    try:
        text, lang, source = client.fetch_transcript(
            _VIDEO_ID,
            languages=settings.transcript_language_preference,
        )
    except TranscriptRateLimited:
        pytest.skip("YouTube throttled the request (HTTP 429); transient environment issue")

    assert text and text.strip(), "expected non-empty transcript text"
    assert len(text) > 200, f"transcript unexpectedly short ({len(text)} chars)"
    assert " " in text.strip(), "expected human-readable words, not a single token"
    assert source == "youtube_timedtext"
    if lang is not None:
        assert isinstance(lang, str) and lang, "language code should be a non-empty string when present"
