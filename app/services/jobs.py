from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

log = logging.getLogger("quant_allinpodcast.jobs")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def submit(self, kind: str, fn: Callable[[], Any], key: str | None = None) -> dict[str, Any]:
        with self._lock:
            for job in self._jobs.values():
                if key and job.get("key") == key and job["status"] in {"queued", "running"}:
                    return job
            jid = str(uuid.uuid4())
            job = {
                "id": jid,
                "kind": kind,
                "key": key,
                "status": "queued",
                "created_at": _now(),
                "updated_at": _now(),
                "result": None,
                "error": None,
            }
            self._jobs[jid] = job

        def _runner():
            self._update(jid, status="running")
            try:
                result = fn()
                self._update(jid, status="done", result=result)
            except Exception as exc:
                log.exception("job failed: %s", jid)
                self._update(jid, status="failed", error=str(exc))

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        return job

    def _update(self, jid: str, **updates) -> None:
        with self._lock:
            job = self._jobs[jid]
            job.update(updates)
            job["updated_at"] = _now()

    def get(self, jid: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(jid)
            return dict(job) if job else None


registry = JobRegistry()
