from __future__ import annotations

import logging
from typing import Any

import httpx

from app.models.domain import Episode
from app.models.llm_schemas import SentimentObservation, SentimentOutput

log = logging.getLogger("quant_allinpodcast.sentiment")

SENTIMENT_SYSTEM = (
    "You are a market-sentiment classifier. Given a distilled podcast summary, "
    "return ONLY a JSON object: "
    '{"observations": [{"subject_type": "ticker|sector|theme|market", '
    '"subject": "AAPL or sector/theme name or ALL", '
    '"sentiment_label": "bullish|bearish|neutral", '
    '"sentiment_score": -1.0..1.0, "confidence": 0.0..1.0, '
    '"horizon": "intraday|1d|5d|30d", "reason": "short rationale"}]}. '
    "Include one observation per ticker/sector/theme discussed, plus one "
    'subject_type "market" with subject "ALL" for the overall tone.'
)


def idempotency_key(video_id: str, subject: str, model: str, prompt_version: str) -> str:
    return f"allin:{video_id}:{subject}:{model}:{prompt_version}"


def extract_sentiment(llm_client, distill_summary: str) -> tuple[SentimentOutput, dict[str, Any]]:
    data, usage = llm_client.complete_json(
        SENTIMENT_SYSTEM,
        f"Distilled summary:\n{distill_summary}\n\nReturn the JSON object.",
    )
    out = SentimentOutput.model_validate(data)
    log.info("sentiment: extracted %d observation(s)", len(out.observations))
    return out, usage


class SentimentApiClient:
    """Delivers sentiment observations to a quant_sentiment-compatible POST /sentiment API."""

    def __init__(
        self,
        *,
        url: str,
        api_key: str = "",
        source: str = "quant_allinpodcast",
        timeout: int = 30,
        client: httpx.Client | None = None,
    ) -> None:
        self.url = url.strip()
        self.source = source
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = client or httpx.Client(timeout=timeout, headers=headers)

    def close(self) -> None:
        self._client.close()

    def deliver(
        self,
        obs: SentimentObservation,
        episode: Episode,
        *,
        model: str,
        prompt_version: str,
    ) -> tuple[bool, str | None]:
        key = idempotency_key(episode.video_id, obs.subject, model, prompt_version)
        body = {
            "source": self.source,
            "idempotency_key": key,
            "subject_type": obs.subject_type,
            "subject": obs.subject,
            "sentiment_label": obs.sentiment_label,
            "sentiment_score": obs.sentiment_score,
            "confidence": obs.confidence,
            "horizon": obs.horizon,
            "reason": obs.reason or "",
            "observed_at": episode.published_at.isoformat() if episode.published_at else None,
            "tags": ["allin", episode.channel_slug] if episode.channel_slug else ["allin"],
            "metadata": {
                "channel": episode.channel_slug,
                "video_id": episode.video_id,
                "title": episode.title,
                "source_url": episode.source_url,
            },
        }

        try:
            resp = self._client.post(self.url, json=body)
        except httpx.HTTPError as exc:
            log.warning("sentiment delivery transport error for %s: %s", key, exc)
            return False, None

        if resp.status_code in (200, 201):
            sid = None
            try:
                sid = (resp.json() or {}).get("sentiment_id")
            except Exception:
                sid = None
            return True, sid

        log.warning("sentiment delivery rejected (%s) for %s", resp.status_code, key)
        return False, None
