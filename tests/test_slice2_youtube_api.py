from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.services.youtube_client import TranscriptRateLimited, YouTubeClient


def _recent_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")


def _client(handler, **kwargs) -> YouTubeClient:
    http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    kwargs.setdefault("api_key", "test-key")
    return YouTubeClient(client=http, **kwargs)


def test_discovery_uses_channel_latest():
    recent = _recent_iso()
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        if request.url.path.endswith("/youtube/channel/latest"):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "videoId": "abcdefghijk",
                            "title": "Episode 1",
                            "published": recent,
                            "link": "https://www.youtube.com/watch?v=abcdefghijk",
                            "description": "desc",
                            "thumbnail": {"url": "https://img/1.jpg"},
                        }
                    ]
                },
            )
        return httpx.Response(404, json={})

    yt = _client(handler, channel_handle="allin")
    items = yt.discover_recent_videos(lookback_days=14, max_items=10)

    assert len(items) == 1
    assert items[0]["video_id"] == "abcdefghijk"
    assert items[0]["channel_slug"] == "allin"
    assert items[0]["source_url"] == "https://www.youtube.com/watch?v=abcdefghijk"
    assert any(p.get("channel") == "@allin" for p in calls)


def test_discovery_supports_multiple_channels():
    recent = _recent_iso()
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        if request.url.path.endswith("/youtube/channel/latest"):
            vid = {"@allin": "abcdefghijk", "@othercast": "zzzzzzzzzzz"}.get(params.get("channel"))
            results = [{"videoId": vid, "title": vid, "published": recent, "thumbnail": {"url": "x"}}] if vid else []
            return httpx.Response(200, json={"results": results})
        return httpx.Response(404, json={})

    yt = _client(handler)
    items = yt.discover_recent_videos(
        lookback_days=14,
        max_items=10,
        channels=[
            {"channel_id": "", "channel_handle": "allin", "channel_slug": "allin"},
            {"channel_id": "", "channel_handle": "othercast", "channel_slug": "other"},
        ],
    )

    assert {item["channel_slug"] for item in items} == {"allin", "other"}
    assert {p.get("channel") for p in calls if "channel" in p} == {"@allin", "@othercast"}


def test_discovery_uses_channel_id_when_present():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        return httpx.Response(200, json={"results": []})

    yt = _client(handler)
    yt.discover_recent_videos(
        channels=[{"channel_id": "UC123", "channel_handle": "ignored", "channel_slug": "x"}],
    )

    assert any(p.get("channel") == "UC123" for p in calls)


def test_discovery_filters_outside_lookback():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": [{"videoId": "abcdefghijk", "title": "Old", "published": "2000-01-01T00:00:00Z", "thumbnail": {}}]},
        )

    yt = _client(handler)
    assert yt.discover_recent_videos(lookback_days=14, max_items=10) == []


def test_discovery_requires_api_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    yt = _client(handler, api_key="")
    with pytest.raises(ValueError, match="TRANSCRIPTAPI_KEY"):
        yt.discover_recent_videos()


def test_fetch_transcript_returns_flattened_text():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/youtube/transcript"):
            return httpx.Response(
                200,
                json={
                    "video_id": "vid123",
                    "language": "en",
                    "transcript": [
                        {"text": "Hello & welcome"},
                        {"text": "to the show"},
                        {"text": "to the show"},
                    ],
                },
            )
        return httpx.Response(404, json={})

    yt = _client(handler)
    text, lang, source = yt.fetch_transcript("vid123", languages=["en", "en-US"])

    assert "Hello & welcome" in text
    assert "to the show" in text
    assert text.count("to the show") == 1  # consecutive rolling-caption dupes collapsed
    assert lang == "en"
    assert source == "transcriptapi"


def test_fetch_transcript_maps_languages_to_transcriptapi_codes():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"language": "en", "transcript": [{"text": "hi"}]})

    yt = _client(handler)
    yt.fetch_transcript("vid123", languages=["en-orig", "en", "en-US", "asr"])

    assert seen["language"] == "en,asr"  # region variants collapse + dedupe, asr preserved


def test_fetch_transcript_404_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "no transcript", "code": "no_transcript"})

    yt = _client(handler)
    with pytest.raises(ValueError, match="transcript unavailable"):
        yt.fetch_transcript("vid404", languages=["en"])


def test_fetch_transcript_rate_limited_is_transient():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": "slow down"})

    yt = _client(handler, retries=1, backoff=0)
    with pytest.raises(TranscriptRateLimited):
        yt.fetch_transcript("vid429", languages=["en"])


def test_fetch_transcript_payment_required_is_transient():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"detail": {"message": "out of credits", "reason": "insufficient_credits"}})

    yt = _client(handler, retries=1, backoff=0)
    with pytest.raises(TranscriptRateLimited):
        yt.fetch_transcript("vid402", languages=["en"])
