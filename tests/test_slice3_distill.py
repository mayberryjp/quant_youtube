from __future__ import annotations

import httpx

from app.services.distill_api import DistillApiClient


class FakeHttpClient:
    def __init__(self, body, status_code=200):
        self.body = body
        self.status_code = status_code
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return httpx.Response(
            self.status_code,
            json=self.body,
            request=httpx.Request("POST", url),
        )


class TestDistillApiClient:
    def test_posts_process_payload(self):
        body = {
            "status": "ok",
            "request_id": "request-1",
            "distillation": {"summary": "summary", "key_topics": [], "segments": []},
        }
        http = FakeHttpClient(body)
        client = DistillApiClient(base_url="http://distill.local/", client=http)
        payload = {"source": "youtube", "text": "transcript"}

        assert client.process(payload) == body
        assert http.calls == [
            ("http://distill.local/v1/process", {"json": payload, "timeout": 3600})
        ]

    def test_rejects_invalid_success_response(self):
        client = DistillApiClient(
            base_url="http://distill.local",
            client=FakeHttpClient({"status": "ok"}),
        )

        try:
            client.process({"text": "transcript"})
        except ValueError as exc:
            assert "invalid process response" in str(exc)
        else:
            raise AssertionError("expected invalid response to fail")
