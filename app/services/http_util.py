"""HTTP helpers: bounded exponential-backoff retry for outbound calls."""

from __future__ import annotations

import logging
import time
from typing import Callable

import httpx

log = logging.getLogger("youtube.http")


def request_with_retry(
    fn: Callable[[], httpx.Response],
    *,
    retries: int = 3,
    backoff: float = 1.0,
    retry_on_timeout: bool = True,
) -> httpx.Response:
    """Call ``fn`` (which issues one request), retrying on 5xx / transport errors.

    4xx responses are returned immediately (not retried). Raises the last
    transport error if every attempt fails at the transport level. Set
    ``retry_on_timeout=False`` for expensive calls where a timeout means the
    server is still working and a retry would only duplicate the load.
    """
    last_exc: Exception | None = None
    last_resp: httpx.Response | None = None
    for attempt in range(retries + 1):
        try:
            resp = fn()
        except httpx.TimeoutException as exc:
            if not retry_on_timeout:
                raise
            last_exc = exc
        except httpx.HTTPError as exc:  # transport-level failure
            last_exc = exc
        else:
            if resp.status_code < 500:
                return resp
            last_resp = resp
        if attempt < retries:
            time.sleep(backoff * (2 ** attempt))
    if last_resp is not None:
        return last_resp
    assert last_exc is not None
    raise last_exc
