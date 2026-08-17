from __future__ import annotations

import logging
from datetime import date

from bottle import Bottle, HTTPResponse, request

from app import dependencies as deps
from app.config import settings
from app.models.responses import IngestRunListResponse, IngestRunResponse

sub = Bottle()
log = logging.getLogger("youtube.runs")


def _json_error(status: int, detail) -> HTTPResponse:
    return HTTPResponse(status=status, body={"detail": detail})


def _page_params() -> tuple[int, int | None]:
    if "page" not in request.params and "page_size" not in request.params:
        return 1, None
    page = max(int(request.params.get("page") or 1), 1)
    page_size = int(request.params.get("page_size") or settings.default_page_size)
    page_size = max(page_size, 1)
    return page, page_size


def _date_param(name: str):
    raw = request.params.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise _json_error(422, f"{name} must be YYYY-MM-DD")


@sub.get("/allin/runs")
def list_runs():
    try:
        page, page_size = _page_params()
        repo = deps.run_repo()
        items, total = repo.list(
            status=request.params.get("status"),
            from_date=_date_param("from_date"),
            to_date=_date_param("to_date"),
            page=page,
            page_size=page_size,
        )
        payload = IngestRunListResponse(
            items=[IngestRunResponse.model_validate(item.model_dump(mode="json")) for item in items],
            total=total,
            page=page,
            page_size=total if page_size is None else page_size,
        )
        return payload.model_dump(mode="json")
    except HTTPResponse:
        raise
    except Exception as exc:
        log.exception("failed to list ingest runs")
        raise _json_error(500, f"failed to list ingest runs: {exc}")


@sub.get("/allin/runs/<run_date>")
def get_run(run_date: str):
    try:
        parsed = date.fromisoformat(run_date)
    except ValueError:
        raise _json_error(422, "run_date must be YYYY-MM-DD")

    try:
        repo = deps.run_repo()
        run = repo.get_by_run_date(parsed)
        if run is None:
            raise _json_error(404, "Run not found")
        return IngestRunResponse.model_validate(run.model_dump(mode="json")).model_dump(mode="json")
    except HTTPResponse:
        raise
    except Exception as exc:
        log.exception("failed to load ingest run %s", run_date)
        raise _json_error(500, f"failed to load ingest run: {exc}")
