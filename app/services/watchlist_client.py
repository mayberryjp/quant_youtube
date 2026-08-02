from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.models.domain import Episode


class WatchlistClient:
    def __init__(
        self,
        *,
        api_url: str,
        api_key: str = "",
        source: str = "quant_allinpodcast",
        timeout: int = 15,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_url = api_url.strip()
        self.source = source
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.client = client or httpx.Client(timeout=timeout, headers=headers)

    def close(self) -> None:
        self.client.close()

    def publish(
        self,
        *,
        episode: Episode,
        symbols: list[str],
        summary: str,
        key_topics: list[str],
        model: str,
        prompt_version: str,
    ) -> dict[str, Any]:
        payload = {
            "source": self.source,
            "episode_id": episode.id,
            "video_id": episode.video_id,
            "channel_slug": episode.channel_slug,
            "title": episode.title,
            "published_at": _iso_or_none(episode.published_at),
            "source_url": episode.source_url,
            "model": model,
            "prompt_version": prompt_version,
            "symbols": symbols,
            "key_topics": key_topics,
            "summary": summary,
        }
        resp = self.client.post(self.api_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {"result": data}


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
