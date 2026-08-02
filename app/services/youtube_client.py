from __future__ import annotations

import hashlib
import html
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger("quant_allinpodcast.youtube")
_RFC3339_Z_SUFFIX = "+00:00"


class YouTubeClient:
    def __init__(
        self,
        *,
        api_base_url: str,
        api_key: str,
        channel_id: str = "",
        channel_handle: str = "allin",
        channel_slug: str = "allin",
        timeout: int = 30,
        retries: int = 3,
        backoff: float = 1.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key
        self.channel_id = channel_id
        self.channel_handle = channel_handle.lstrip("@")
        self.channel_slug = channel_slug
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True)

    def close(self) -> None:
        self.client.close()

    def discover_recent_videos(
        self,
        *,
        lookback_days: int = 14,
        max_items: int = 80,
        channels: list[dict[str, str]] | None = None,
    ) -> list[dict]:
        if not self.api_key:
            raise ValueError("ALLIN_YOUTUBE_API_KEY is required for official YouTube API discovery")

        targets = channels or [{
            "channel_id": self.channel_id,
            "channel_handle": self.channel_handle,
            "channel_slug": self.channel_slug,
        }]

        floor = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        floor_iso = floor.isoformat().replace(_RFC3339_Z_SUFFIX, "Z")

        all_items: list[dict] = []
        seen: set[str] = set()
        for target in targets:
            if len(all_items) >= max_items:
                break
            channel_id = self._resolve_channel_id(
                channel_id=(target.get("channel_id") or ""),
                channel_handle=(target.get("channel_handle") or self.channel_handle),
            )
            channel_slug = (target.get("channel_slug") or self.channel_slug or "allin").strip()
            token: str | None = None

            while len(all_items) < max_items:
                remaining = max_items - len(all_items)
                payload = self._request_json(
                    "/youtube/v3/search",
                    params={
                        "part": "snippet",
                        "channelId": channel_id,
                        "order": "date",
                        "type": "video",
                        "maxResults": min(50, remaining),
                        "publishedAfter": floor_iso,
                        "pageToken": token,
                        "key": self.api_key,
                    },
                )
                for row in payload.get("items", []):
                    vid = ((row.get("id") or {}).get("videoId") or "").strip()
                    if not vid or vid in seen:
                        continue
                    seen.add(vid)
                    snippet = row.get("snippet") or {}
                    thumbs = snippet.get("thumbnails") or {}
                    thumb_url = (
                        (thumbs.get("high") or {}).get("url")
                        or (thumbs.get("medium") or {}).get("url")
                        or (thumbs.get("default") or {}).get("url")
                    )
                    all_items.append(
                        {
                            "video_id": vid,
                            "channel_slug": channel_slug,
                            "title": snippet.get("title"),
                            "published_at": _parse_published_at(snippet.get("publishedAt")),
                            "source_url": f"https://www.youtube.com/watch?v={vid}",
                            "thumbnail_url": thumb_url,
                            "description": snippet.get("description"),
                            "duration_seconds": None,
                        }
                    )
                    if len(all_items) >= max_items:
                        break

                token = payload.get("nextPageToken")
                if not token:
                    break

        all_items.sort(key=lambda x: x.get("published_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return all_items[:max_items]

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

    def _resolve_channel_id(self, *, channel_id: str = "", channel_handle: str = "") -> str:
        if channel_id:
            return channel_id

        handle = (channel_handle or self.channel_handle).lstrip("@").strip()
        if not handle:
            raise ValueError("channel handle is required when channel_id is not provided")

        if handle == self.channel_handle and self.channel_id:
            return self.channel_id

        payload = self._request_json(
            "/youtube/v3/channels",
            params={
                "part": "id",
                "forHandle": handle,
                "maxResults": 1,
                "key": self.api_key,
            },
        )
        items = payload.get("items") or []
        if not items:
            raise ValueError(f"Could not resolve YouTube handle '@{handle}'")
        cid = (items[0] or {}).get("id")
        if not cid:
            raise ValueError("YouTube channels response missing id")
        if handle == self.channel_handle:
            self.channel_id = cid
        return cid

    def _request_json(self, path: str, *, params: dict) -> dict:
        url = f"{self.api_base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.client.get(url, params={k: v for k, v in params.items() if v is not None})
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                last_exc = exc
                if attempt >= self.retries:
                    break
                sleep_for = self.backoff * (2 ** (attempt - 1))
                time.sleep(sleep_for)
        raise RuntimeError(f"YouTube API request failed for {path}") from last_exc


def _parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", _RFC3339_Z_SUFFIX))
    except ValueError:
        return None


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
