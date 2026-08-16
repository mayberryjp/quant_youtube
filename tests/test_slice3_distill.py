from __future__ import annotations

import httpx
import pytest

from app.services.distill_api import DistillApiClient, DistillJobFailed, DistillJobTimeout

RESULT = {
    "status": "ok",
    "request_id": "request-1",
    "distillation": {"summary": "summary", "key_topics": [], "segments": []},
}


class FakeHttpClient:
    """Serves one POST response then a scripted sequence of GET job payloads."""

    def __init__(self, submit_body, job_bodies=(), submit_status=202):
        self.submit_body = submit_body
        self.submit_status = submit_status
        self.job_bodies = list(job_bodies)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return httpx.Response(
            self.submit_status,
            json=self.submit_body,
            request=httpx.Request("POST", url),
        )

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return httpx.Response(
            200,
            json=self.job_bodies.pop(0),
            request=httpx.Request("GET", url),
        )


def _client(http, **kwargs):
    kwargs.setdefault("poll_interval", 0)
    return DistillApiClient(base_url="http://distill.local/", client=http, **kwargs)


class TestDistillApiClient:
    def test_submit_returns_job_id(self):
        http = FakeHttpClient({"status": "accepted", "job_id": "job-1", "job_status": "queued"})
        payload = {"source": "youtube", "text": "transcript"}

        assert _client(http).submit(payload) == "job-1"
        assert http.calls == [
            ("POST", "http://distill.local/v1/process", {"json": payload, "timeout": 30})
        ]

    def test_submit_without_job_id_fails(self):
        http = FakeHttpClient({"status": "accepted"})

        with pytest.raises(ValueError, match="job_id"):
            _client(http).submit({"text": "transcript"})

    def test_polls_until_succeeded(self):
        http = FakeHttpClient(
            {"job_id": "job-1"},
            job_bodies=[
                {"status": "queued", "result": None},
                {"status": "running", "result": None},
                {"status": "succeeded", "result": RESULT},
            ],
        )

        assert _client(http).wait_for_result("job-1") == RESULT
        assert [c[1] for c in http.calls] == ["http://distill.local/v1/jobs/job-1"] * 3

    def test_failed_job_raises(self):
        http = FakeHttpClient(
            {"job_id": "job-1"},
            job_bodies=[{"status": "failed", "error": "llm distill call failed"}],
        )

        with pytest.raises(DistillJobFailed, match="llm distill call failed"):
            _client(http).wait_for_result("job-1")

    def test_gives_up_after_job_timeout(self):
        http = FakeHttpClient({"job_id": "job-1"}, job_bodies=[{"status": "running"}])

        with pytest.raises(DistillJobTimeout, match="job-1"):
            _client(http, job_timeout=0).wait_for_result("job-1")

    def test_rejects_invalid_success_response(self):
        http = FakeHttpClient(
            {"job_id": "job-1"},
            job_bodies=[{"status": "succeeded", "result": {"status": "ok"}}],
        )

        with pytest.raises(ValueError, match="invalid process response"):
            _client(http).wait_for_result("job-1")
