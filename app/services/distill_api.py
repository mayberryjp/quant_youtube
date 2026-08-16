"""Client for the shared quant_distill processing API.

``POST /v1/process`` is asynchronous: it enqueues a job and returns 202 + ``job_id``.
The result is collected by polling ``GET /v1/jobs/{job_id}``.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.services.http_util import request_with_retry


class DistillJobFailed(RuntimeError):
    """The distill job reached the terminal ``failed`` state."""


class DistillJobTimeout(RuntimeError):
    """The job was still queued/running when polling gave up; it keeps running server-side."""


class DistillApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        submit_timeout: int = 30,
        poll_interval: int = 20,
        job_timeout: int = 3600,
        retries: int = 3,
        backoff: float = 1.0,
        client: httpx.Client | None = None,
    ) -> None:
        base = base_url.rstrip("/")
        self.url = f"{base}/v1/process"
        self.jobs_url = f"{base}/v1/jobs"
        self.submit_timeout = submit_timeout
        self.poll_interval = poll_interval
        self.job_timeout = job_timeout
        self.retries = retries
        self.backoff = backoff
        self.client = client or httpx.Client()

    def submit(self, payload: dict[str, Any]) -> str:
        """Enqueue a process job and return its ``job_id``."""
        response = request_with_retry(
            lambda: self.client.post(self.url, json=payload, timeout=self.submit_timeout),
            retries=self.retries,
            backoff=self.backoff,
            # A retried submit would create a second job and a second set of LLM calls.
            retry_on_timeout=False,
        )
        response.raise_for_status()
        body = response.json()
        job_id = body.get("job_id")
        if not job_id:
            raise ValueError("quant_distill did not return a job_id for the process request")
        return str(job_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        response = request_with_retry(
            lambda: self.client.get(f"{self.jobs_url}/{job_id}", timeout=self.submit_timeout),
            retries=self.retries,
            backoff=self.backoff,
        )
        response.raise_for_status()
        return response.json()

    def wait_for_result(self, job_id: str) -> dict[str, Any]:
        """Poll until the job succeeds, fails, or ``job_timeout`` elapses."""
        deadline = time.monotonic() + self.job_timeout
        while True:
            job = self.get_job(job_id)
            status = job.get("status")
            if status == "succeeded":
                result = job.get("result")
                if not isinstance(result, dict) or not isinstance(result.get("distillation"), dict):
                    raise ValueError("quant_distill returned an invalid process response")
                return result
            if status == "failed":
                raise DistillJobFailed(job.get("error") or f"distill job {job_id} failed")
            if time.monotonic() + self.poll_interval >= deadline:
                raise DistillJobTimeout(
                    f"distill job {job_id} still {status} after {self.job_timeout}s"
                )
            time.sleep(self.poll_interval)
