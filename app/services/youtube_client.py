"""YouTube integration backed by transcriptapi.com.

Both stages of the pipeline go through this single client:
  * discovery  -> GET /youtube/channel/latest  (free RSS feed, exact publish times)
  * transcripts -> GET /youtube/transcript      (1 credit, charged only on 200)

The public surface (``discover_recent_videos`` / ``fetch_transcript`` /
``TranscriptRateLimited`` / ``content_hash``) is unchanged, so the discovery and
transcript services do not need to know which provider is underneath.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from time import perf_counter, sleep

import httpx

log = logging.getLogger("quant_allinpodcast.youtube")

_RFC3339_Z_SUFFIX = "+00:00"
_DEFAULT_BASE_URL = "https://transcriptapi.com/api/v2"
# Statuses worth an in-client retry (transient network / throttling / server blips).
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
# Statuses that mean "try again later" rather than a permanent failure for this video.
# 402 (out of credits) is included so episodes stay retryable once credits are topped up.
_TRANSIENT_STATUS = {402, 408, 429, 500, 502, 503, 504}


class TranscriptRateLimited(Exception):
    """transcriptapi.com signalled a transient condition (429/402/5xx); keep the episode retryable."""


class YouTubeClient:
    """Thin HTTP client over transcriptapi.com for discovery + transcript extraction."""

    def __init__(
        self,
        *,
        api_base_url: str = _DEFAULT_BASE_URL,
        api_key: str = "",
        channel_id: str = "",
        channel_handle: str = "allin",
        channel_slug: str = "allin",
        timeout: int = 30,
        retries: int = 3,
        backoff: float = 1.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_base_url = (api_base_url or _DEFAULT_BASE_URL).rstrip("/")
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

    # -- discovery ---------------------------------------------------------

    def discover_recent_videos(
        self,
        *,
        lookback_days: int = 14,
        max_items: int = 80,
        channels: list[dict[str, str]] | None = None,
    ) -> list[dict]:
        if not self.api_key:
            raise ValueError("TRANSCRIPTAPI_KEY is required for transcriptapi.com discovery")

        targets = channels or [{
            "channel_id": self.channel_id,
            "channel_handle": self.channel_handle,
            "channel_slug": self.channel_slug,
        }]
        floor = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        log.info("discovery: crawling %d channel(s), lookback=%dd, max_items=%d", len(targets), lookback_days, max_items)

        items: list[dict] = []
        seen: set[str] = set()
        for target in targets:
            channel_ref = self._channel_ref(target)
            if not channel_ref:
                log.warning("discovery: skipping target with no channel id/handle: %r", target)
                continue
            channel_slug = (target.get("channel_slug") or self.channel_slug or "allin").strip()

            payload = self._get("/youtube/channel/latest", params={"channel": channel_ref})
            rows = payload.get("results", [])
            kept = 0
            for row in rows:
                vid = (row.get("videoId") or "").strip()
                if not vid or vid in seen:
                    continue
                published = _parse_published_at(row.get("published"))
                if published is not None and published < floor:
                    continue
                seen.add(vid)
                kept += 1
                items.append(
                    {
                        "video_id": vid,
                        "channel_slug": channel_slug,
                        "title": row.get("title"),
                        "published_at": published,
                        "source_url": row.get("link") or f"https://www.youtube.com/watch?v={vid}",
                        "thumbnail_url": (row.get("thumbnail") or {}).get("url"),
                        "description": row.get("description"),
                        "duration_seconds": None,
                    }
                )
            log.info("discovery: %s -> %d returned, %d within lookback", channel_ref, len(rows), kept)

        items.sort(
            key=lambda x: x.get("published_at") or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        result = items[:max_items]
        log.info("discovery: %d unique video(s) selected", len(result))
        return result

    def _channel_ref(self, target: dict[str, str]) -> str:
        channel_id = (target.get("channel_id") or "").strip()
        if channel_id:
            return channel_id
        handle = (target.get("channel_handle") or self.channel_handle).lstrip("@").strip()
        return f"@{handle}" if handle else ""

    # -- transcripts -------------------------------------------------------

    def fetch_transcript(self, video_id: str, *, languages: list[str] | None = None) -> tuple[str, str | None, str]:
        detail = self.fetch_transcript_detail(video_id, languages=languages)
        return detail["text"], detail["language"], detail["source"]

    def fetch_transcript_detail(self, video_id: str, *, languages: list[str] | None = None) -> dict:
        """Like ``fetch_transcript`` but also surfaces ``length_seconds`` from the response."""
        codes = _normalize_languages(languages) or ["en", "asr"]
        log.debug("transcript: fetching %s (languages=%s)", video_id, codes)
        status, payload, _headers = self._request(
            "/youtube/transcript",
            params={
                "video_url": video_id,
                "format": "json",
                "include_timestamp": "false",
                "language": ",".join(codes),
            },
        )

        if status == 200:
            text = _flatten_segments(payload.get("transcript") or [])
            if text:
                length = payload.get("length_seconds")
                length_seconds = length if isinstance(length, int) and not isinstance(length, bool) else None
                log.debug(
                    "transcript: %s -> %d chars, language=%s, length=%ss",
                    video_id, len(text), payload.get("language"), length_seconds,
                )
                return {
                    "text": text,
                    "language": payload.get("language"),
                    "source": "transcriptapi",
                    "length_seconds": length_seconds,
                }
            raise ValueError("transcript unavailable")

        if status in _TRANSIENT_STATUS:
            raise TranscriptRateLimited(f"transcriptapi {status} for {video_id}: {_detail_message(payload)}")
        if status == 404:
            raise ValueError("transcript unavailable")
        raise RuntimeError(f"transcriptapi {status} for {video_id}: {_detail_message(payload)}")

    def available_languages(self, video_id: str) -> list[dict]:
        """Free /youtube/info lookup returning ``[{code, name}, ...]``; used by diagnostics."""
        status, payload, _headers = self._request("/youtube/info", params={"video_url": video_id})
        if status == 200:
            return payload.get("available_languages") or []
        if status in _TRANSIENT_STATUS:
            raise TranscriptRateLimited(f"transcriptapi {status}: {_detail_message(payload)}")
        return []

    # -- HTTP --------------------------------------------------------------

    def _get(self, path: str, *, params: dict) -> dict:
        status, payload, _headers = self._request(path, params=params)
        if status != 200:
            raise RuntimeError(f"transcriptapi {status} for {path}: {_detail_message(payload)}")
        return payload

    def _request(self, path: str, *, params: dict) -> tuple[int, dict, dict]:
        url = f"{self.api_base_url}{path}"
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        clean = {k: v for k, v in params.items() if v is not None}
        status, payload, resp_headers = 0, {}, {}
        for attempt in range(1, max(1, self.retries) + 1):
            started = perf_counter()
            try:
                resp = self.client.get(url, params=clean, headers=headers)
            except Exception:
                log.warning("transcriptapi GET %s failed (attempt %d/%d)", path, attempt, self.retries, exc_info=True)
                if attempt >= self.retries:
                    raise
                sleep(self.backoff * (2 ** (attempt - 1)))
                continue
            status = resp.status_code
            resp_headers = dict(resp.headers)
            payload = _json_or_detail(resp)
            log.debug(
                "transcriptapi GET %s -> %d in %.2fs (attempt %d/%d, cache=%s, remaining=%s)",
                path, status, perf_counter() - started, attempt, self.retries,
                resp_headers.get("X-Cache-Status"), resp_headers.get("X-RateLimit-Remaining"),
            )
            if status not in _RETRYABLE_STATUS or attempt >= self.retries:
                if status >= 400:
                    log.warning("transcriptapi GET %s -> %d: %s", path, status, _detail_message(payload))
                return status, payload, resp_headers
            log.info("transcriptapi GET %s -> %d, retrying (attempt %d/%d)", path, status, attempt, self.retries)
            self._sleep_for_retry(resp, attempt)
        return status, payload, resp_headers

    def _sleep_for_retry(self, resp: httpx.Response, attempt: int) -> None:
        retry_after = resp.headers.get("Retry-After")
        try:
            delay = float(retry_after) if retry_after else self.backoff * (2 ** (attempt - 1))
        except ValueError:
            delay = self.backoff * (2 ** (attempt - 1))
        sleep(min(delay, 30.0))


# -- module helpers --------------------------------------------------------

def _json_or_detail(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except Exception:
        return {"detail": (resp.text or "").strip()}
    return data if isinstance(data, dict) else {"data": data}


def _detail_message(payload: dict) -> str:
    detail = payload.get("detail")
    if isinstance(detail, dict):  # 402 payment errors carry a nested object
        return str(detail.get("message") or detail)
    return str(detail) if detail is not None else ""


def _normalize_languages(languages: list[str] | None) -> list[str]:
    """Map app language prefs onto transcriptapi codes (region-stripped, deduped, max 10)."""
    out: list[str] = []
    for raw in languages or []:
        code = (raw or "").strip().lower()
        if not code:
            continue
        norm = code if (code == "asr" or code.startswith("asr-")) else code.split("-")[0]
        if norm and norm not in out:
            out.append(norm)
    return out[:10]


def _flatten_segments(segments: list[dict]) -> str:
    lines: list[str] = []
    for seg in segments:
        text = re.sub(r"\s+", " ", seg.get("text") or "").strip()
        if text and (not lines or lines[-1] != text):  # drop rolling-caption repeats
            lines.append(text)
    return "\n".join(lines).strip()


def _parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", _RFC3339_Z_SUFFIX))
    except ValueError:
        return None


def content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
