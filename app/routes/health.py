"""Health, readiness, and basic stats routes."""

from __future__ import annotations

from bottle import Bottle, response

from app import db
from app import dependencies as deps
from app.repository.runs import RunRepository

sub = Bottle()


@sub.get("/allin/health")
def health():
    return {"status": "ok"}


@sub.get("/allin/ready")
def readiness():
    try:
        db.ping()
    except Exception as exc:
        response.status = 503
        return {"status": "not_ready", "detail": str(exc)}
    return {"status": "ok"}


@sub.get("/allin/stats")
def stats():
    try:
        episodes_total = deps.episode_repo().count_total()
        repo = RunRepository(db.get_engine())
        return repo.stats(episodes_total=episodes_total)
    except Exception:
        return {
            "episodes_discovered": 0,
            "transcripts_fetched": 0,
            "distilled": 0,
            "reprocessed": 0,
            "failures": 0,
            "episodes_total": 0,
            "last_run_date": None,
            "last_run_status": None,
            "last_heartbeat": None,
        }
