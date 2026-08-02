from __future__ import annotations

import json

from bottle import Bottle, HTTPResponse, request, response
from pydantic import ValidationError

from app import dependencies as deps
from app.config import settings
from app.models.requests import ReprocessRequest, RetryFailedRequest, RunTriggerRequest
from app.models.responses import DistillationResponse, EpisodeDetailResponse, EpisodeResponse
from app.services.ingest_worker import build_pipeline
from app.services.jobs import registry

sub = Bottle()


def _json_error(status: int, detail) -> HTTPResponse:
    return HTTPResponse(status=status, body={"detail": detail})


def _page_params() -> tuple[int, int]:
    page = max(int(request.params.get("page") or 1), 1)
    page_size = int(request.params.get("page_size") or settings.default_page_size)
    page_size = max(1, min(page_size, settings.max_page_size))
    return page, page_size


@sub.get("/episodes")
def list_episodes():
    page, page_size = _page_params()
    repo = deps.episode_repo()
    items, total = repo.list(
        status=request.params.get("status"),
        from_date=request.params.get("from_date"),
        to_date=request.params.get("to_date"),
        page=page,
        page_size=page_size,
    )
    summaries = deps.distillation_repo().get_current_map([e.id for e in items])
    return {
        "items": [
            EpisodeResponse(
                **e.model_dump(),
                summary=(summaries[e.id].summary if e.id in summaries else None),
            ).model_dump(mode="json")
            for e in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@sub.get("/episodes/<episode_id:int>")
def get_episode(episode_id: int):
    repo = deps.episode_repo()
    e = repo.get_by_id(episode_id)
    if e is None:
        raise _json_error(404, "Episode not found")
    current = deps.distillation_repo().get_current(episode_id)
    detail = EpisodeDetailResponse(
        **e.model_dump(),
        summary=(current.summary if current else None),
        distillation=(DistillationResponse(**current.model_dump()) if current else None),
    )
    return detail.model_dump(mode="json")


@sub.post("/episodes/<video_id>/reprocess")
def reprocess_one(video_id: str):
    pipeline = build_pipeline()
    e = pipeline.episodes.get_by_identifier(video_id)
    if e is None:
        raise _json_error(404, "Episode not found")

    job = registry.submit("reprocess", lambda: pipeline.reprocess(e), key=f"reprocess:{video_id}")
    response.status = 202
    return {
        "status": "accepted",
        "job_id": job["id"],
        "job_status": job["status"],
        "video_id": video_id,
    }


@sub.post("/episodes/<video_id>/restart")
def restart_one(video_id: str):
    pipeline = build_pipeline()
    e = pipeline.episodes.get_by_identifier(video_id)
    if e is None:
        raise _json_error(404, "Episode not found")

    job = registry.submit("restart", lambda: pipeline.restart(e), key=f"restart:{video_id}")
    response.status = 202
    return {
        "status": "accepted",
        "job_id": job["id"],
        "job_status": job["status"],
        "video_id": video_id,
    }


@sub.get("/jobs/<job_id>")
def get_job(job_id: str):
    job = registry.get(job_id)
    if not job:
        raise _json_error(404, "Job not found")
    return job


@sub.post("/reprocess")
def reprocess_bulk():
    try:
        body = ReprocessRequest(**(request.json or {}))
    except ValidationError as e:
        raise _json_error(422, json.loads(e.json()))

    pipeline = build_pipeline()
    candidates = pipeline.episodes.reprocess_candidates(
        from_date=body.from_date,
        to_date=body.to_date,
        only_stale=body.only_stale,
        current_model=settings.llm_model,
        current_prompt=settings.distill_prompt_version,
    )

    def _job():
        for e in candidates:
            pipeline.reprocess(e)
        return {"reprocessed": len(candidates)}

    job = registry.submit("reprocess-bulk", _job)
    response.status = 202
    return {
        "status": "accepted",
        "job_id": job["id"],
        "job_status": job["status"],
        "matched": len(candidates),
        "video_ids": [e.video_id for e in candidates],
    }


@sub.post("/runs/trigger")
def trigger_run():
    try:
        body = RunTriggerRequest(**(request.json or {}))
    except ValidationError as e:
        raise _json_error(422, json.loads(e.json()))

    def _job():
        return build_pipeline().run(run_date=body.run_date)

    job = registry.submit("run-trigger", _job)
    response.status = 202
    return {"status": "accepted", "job_id": job["id"], "job_status": job["status"]}


@sub.post("/retry-failed")
def retry_failed():
    try:
        body = RetryFailedRequest(**(request.json or {}))
    except ValidationError as e:
        raise _json_error(422, json.loads(e.json()))

    def _job():
        kwargs = {
            "from_date": body.from_date,
            "to_date": body.to_date,
            "max_attempts": body.max_attempts,
        }
        if body.delete_after_attempts is not None:
            kwargs["delete_after_attempts"] = body.delete_after_attempts
        return build_pipeline().retry_failed(**kwargs)

    job = registry.submit("retry-failed", _job)
    response.status = 202
    return {"status": "accepted", "job_id": job["id"], "job_status": job["status"]}
