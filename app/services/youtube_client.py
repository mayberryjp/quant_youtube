from __future__ import annotations

import hashlib
import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger("quant_allinpodcast.youtube")
_VIDEO_ID = re.compile(r"\"videoId\":\"([a-zA-Z0-9_-]{11})\"")


class YouTubeClient:
    def __init__(
        self,
        *,
        channel_url: str,
        timeout: int = 30,
        retries: int = 3,
        backoff: float = 1.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.channel_url = channel_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True)

    def close(self) -> None:
        self.client.close()

    def discover_recent_videos(self, *, lookback_days: int = 14, max_items: int = 80) -> list[dict]:
        videos_url = f"{self.channel_url}/videos"
        text = self.client.get(videos_url).text
        ids: list[str] = []
        for m in _VIDEO_ID.finditer(text):
            vid = m.group(1)
            if vid not in ids:
                ids.append(vid)
            if len(ids) >= max_items:
                break

        now = datetime.now(timezone.utc)
        floor = now - timedelta(days=lookback_days)
        items: list[dict] = []
        for vid in ids:
            item = {
                "video_id": vid,
                "channel_slug": "allin",
                "title": None,
                "published_at": floor,
                "source_url": f"https://www.youtube.com/watch?v={vid}",
                "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                "description": None,
                "duration_seconds": None,
            }
            items.append(item)
        return items

    def fetch_transcript(self, video_id: str, *, languages: list[str] | None = None) -> tuple[str, str | None, str]:
        languages = languages or ["en", "en-US"]
        for lang in languages:
            url = "https://www.youtube.com/api/timedtext"
            resp = self.client.get(url, params={"v": video_id, "lang": lang, "fmt": "srv3"})
            if resp.status_code != 200 or not resp.text.strip():
                continue
            text = _parse_srv(resp.text)
            if text:
                return text, lang, "youtube_timedtext"
        raise ValueError("transcript unavailable")


def _parse_srv(body: str) -> str:
    root = ET.fromstring(body)
    chunks: list[str] = []
    for node in root.findall(".//text"):
        raw = "".join(node.itertext())
        cleaned = re.sub(r"\s+", " ", html.unescape(raw)).strip()
        if cleaned:
            chunks.append(cleaned)
    return "\n".join(chunks).strip()


def content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
