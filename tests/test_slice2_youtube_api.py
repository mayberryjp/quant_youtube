from __future__ import annotations

import httpx

from app.services.youtube_client import YouTubeClient


def test_discovery_uses_official_youtube_api():
    calls: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((str(request.url), dict(request.url.params)))
        if request.url.path.endswith("/youtube/v3/channels"):
            return httpx.Response(200, json={"items": [{"id": "UC123"}]})
        if request.url.path.endswith("/youtube/v3/search"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": {"videoId": "abcdefghijk"},
                            "snippet": {
                                "title": "Episode 1",
                                "publishedAt": "2026-08-01T10:00:00Z",
                                "description": "desc",
                                "thumbnails": {"high": {"url": "https://img/1.jpg"}},
                            },
                        }
                    ]
                },
            )
        return httpx.Response(404, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    yt = YouTubeClient(
        api_base_url="https://www.googleapis.com",
        api_key="test-key",
        channel_handle="allin",
        client=client,
    )

    items = yt.discover_recent_videos(lookback_days=14, max_items=10)

    assert len(items) == 1
    assert items[0]["video_id"] == "abcdefghijk"
    assert any("/youtube/v3/channels" in url for url, _ in calls)
    assert any("/youtube/v3/search" in url for url, _ in calls)


def test_discovery_supports_multiple_channels():
    calls: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append((str(request.url), params))
        if request.url.path.endswith("/youtube/v3/channels"):
            if params.get("forHandle") == "allin":
                return httpx.Response(200, json={"items": [{"id": "UCALLIN"}]})
            if params.get("forHandle") == "othercast":
                return httpx.Response(200, json={"items": [{"id": "UCOTHER"}]})
            return httpx.Response(200, json={"items": []})
        if request.url.path.endswith("/youtube/v3/search"):
            channel_id = params.get("channelId")
            if channel_id == "UCALLIN":
                return httpx.Response(200, json={"items": [{"id": {"videoId": "abcdefghijk"}, "snippet": {"title": "A", "publishedAt": "2026-08-01T10:00:00Z", "description": "d", "thumbnails": {"high": {"url": "https://img/a.jpg"}}}}]})
            if channel_id == "UCOTHER":
                return httpx.Response(200, json={"items": [{"id": {"videoId": "zzzzzzzzzzz"}, "snippet": {"title": "B", "publishedAt": "2026-08-01T11:00:00Z", "description": "d2", "thumbnails": {"high": {"url": "https://img/b.jpg"}}}}]})
            return httpx.Response(200, json={"items": []})
        return httpx.Response(404, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    yt = YouTubeClient(
        api_base_url="https://www.googleapis.com",
        api_key="test-key",
        client=client,
    )

    items = yt.discover_recent_videos(
        lookback_days=14,
        max_items=10,
        channels=[
            {"channel_id": "", "channel_handle": "allin", "channel_slug": "allin"},
            {"channel_id": "", "channel_handle": "othercast", "channel_slug": "other"},
        ],
    )

    assert len(items) == 2
    assert {item["channel_slug"] for item in items} == {"allin", "other"}
    assert any(p.get("channelId") == "UCALLIN" for _u, p in calls if "channelId" in p)
    assert any(p.get("channelId") == "UCOTHER" for _u, p in calls if "channelId" in p)


def test_fetch_transcript_uses_caption_track_base_url():
    caption_base_url = "https://www.youtube.com/api/timedtext?v=vid123&signature=abc&lang=en"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/youtubei/v1/player":
            return httpx.Response(
                200,
                json={
                    "captions": {
                        "playerCaptionsTracklistRenderer": {
                            "captionTracks": [
                                {"languageCode": "en", "baseUrl": caption_base_url}
                            ]
                        }
                    }
                },
            )
        if request.url.path == "/api/timedtext":
            return httpx.Response(
                200,
                text=(
                    "<transcript>"
                    "<text start=\"0\" dur=\"2\">Hello &amp; welcome</text>"
                    "<text start=\"2\" dur=\"2\">to the show</text>"
                    "</transcript>"
                ),
            )
        return httpx.Response(404, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    yt = YouTubeClient(
        api_base_url="https://www.googleapis.com",
        api_key="test-key",
        innertube_web_key="test-key",
        client=client,
    )

    text, lang, source = yt.fetch_transcript("vid123", languages=["en", "en-US"])

    assert "Hello & welcome" in text
    assert "to the show" in text
    assert lang == "en"
    assert source == "youtube_timedtext"


def test_fetch_transcript_raises_when_no_tracks():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/youtubei/v1/player":
            return httpx.Response(200, json={})
        return httpx.Response(200, text="")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    yt = YouTubeClient(
        api_base_url="https://www.googleapis.com",
        api_key="test-key",
        innertube_web_key="test-key",
        client=client,
    )

    import pytest

    with pytest.raises(ValueError, match="transcript unavailable"):
        yt.fetch_transcript("vid404", languages=["en"])


def test_fetch_transcript_rate_limited_is_transient():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    yt = YouTubeClient(
        api_base_url="https://www.googleapis.com",
        api_key="test-key",
        innertube_web_key="test-key",
        client=client,
        retries=1,
        backoff=0,
    )

    import pytest

    from app.services.youtube_client import TranscriptRateLimited

    with pytest.raises(TranscriptRateLimited):
        yt.fetch_transcript("vid429", languages=["en"])
