from __future__ import annotations

from datetime import datetime

from app.models.domain import Episode
from app.services.sentiment_pass import extract_sentiment, idempotency_key


class FakeLLM:
    def complete_json(self, _system, _user):
        return {
            "observations": [
                {
                    "subject_type": "ticker",
                    "subject": "AAPL",
                    "sentiment_label": "bullish",
                    "sentiment_score": 0.8,
                    "confidence": 0.7,
                    "horizon": "5d",
                    "reason": "positive guidance",
                },
                {
                    "subject_type": "market",
                    "subject": "ALL",
                    "sentiment_label": "neutral",
                },
            ]
        }, {"total_tokens": 12}


class TestSentimentPass:
    def test_extract_sentiment(self):
        out, usage = extract_sentiment(FakeLLM(), "summary")
        assert len(out.observations) == 2
        assert out.observations[0].subject == "AAPL"
        assert usage["total_tokens"] == 12

    def test_idempotency_key(self):
        key = idempotency_key("abcdefghijk", "AAPL", "m1", "v1")
        assert key == "allin:abcdefghijk:AAPL:m1:v1"

    def test_payload_fields(self):
        from app.services.sentiment_pass import SentimentApiClient

        captured = {}

        class C:
            def post(self, _url, json):
                captured.update(json)

                class R:
                    status_code = 201

                    @staticmethod
                    def json():
                        return {"sentiment_id": "sid-1"}

                return R()

        ep = Episode(
            id=1,
            video_id="abcdefghijk",
            channel_slug="allin",
            title="Episode",
            published_at=datetime(2026, 8, 2, 12, 0, 0),
            source_url="https://youtube.com/watch?v=abcdefghijk",
        )
        obs = extract_sentiment(FakeLLM(), "summary")[0].observations[0]
        client = SentimentApiClient(url="http://sentiment.local/sentiment", client=C())
        ok, sid = client.deliver(obs, ep, model="m1", prompt_version="v1")
        assert ok is True
        assert sid == "sid-1"
        assert captured["subject"] == "AAPL"
        assert captured["source"] == "quant_allinpodcast"
