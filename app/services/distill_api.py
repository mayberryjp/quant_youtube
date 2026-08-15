"""Client for the shared quant_distill processing API."""

from __future__ import annotations

from typing import Any

import httpx

from app.services.http_util import request_with_retry


class DistillApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout: int = 180,
        retries: int = 3,
        backoff: float = 1.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.url = f"{base_url.rstrip('/')}/v1/process"
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.client = client or httpx.Client()

    def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = request_with_retry(
            lambda: self.client.post(self.url, json=payload, timeout=self.timeout),
            retries=self.retries,
            backoff=self.backoff,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("status") != "ok" or not isinstance(result.get("distillation"), dict):
            raise ValueError("quant_distill returned an invalid process response")
        return result
