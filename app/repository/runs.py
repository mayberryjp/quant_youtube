from __future__ import annotations

import json
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine


class RunRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def start_run(self, run_date: date) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO allin.ingest_runs (run_date, status, last_heartbeat)
                    VALUES (:run_date, 'running', :heartbeat)
                    ON CONFLICT (run_date) DO UPDATE SET
                        status = 'running',
                        updated_at = CURRENT_TIMESTAMP,
                        last_heartbeat = :heartbeat
                    """
                ),
                {"run_date": run_date, "heartbeat": datetime.now(timezone.utc)},
            )

    def add_counters(self, run_date: date, **counters) -> None:
        keys = [
            "episodes_discovered",
            "transcripts_fetched",
            "distilled",
            "reprocessed",
            "failures",
        ]
        values = {k: int(counters.get(k, 0) or 0) for k in keys}
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE allin.ingest_runs
                    SET episodes_discovered = episodes_discovered + :episodes_discovered,
                        transcripts_fetched = transcripts_fetched + :transcripts_fetched,
                        distilled = distilled + :distilled,
                        reprocessed = reprocessed + :reprocessed,
                        failures = failures + :failures,
                        updated_at = CURRENT_TIMESTAMP,
                        last_heartbeat = :heartbeat
                    WHERE run_date = :run_date
                    """
                ),
                {**values, "run_date": run_date, "heartbeat": datetime.now(timezone.utc)},
            )

    def finish_run(self, run_date: date, status: str, notes: dict | None = None) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE allin.ingest_runs
                    SET status = :status,
                        notes = :notes,
                        updated_at = CURRENT_TIMESTAMP,
                        last_heartbeat = :heartbeat
                    WHERE run_date = :run_date
                    """
                ),
                {
                    "run_date": run_date,
                    "status": status,
                    "notes": json.dumps(notes or {}),
                    "heartbeat": datetime.now(timezone.utc),
                },
            )

    def heartbeat(self) -> None:
        today = datetime.now(timezone.utc).date()
        self.start_run(today)

    def last_run(self) -> dict | None:
        sql = text("SELECT * FROM allin.ingest_runs ORDER BY run_date DESC LIMIT 1")
        with self.engine.connect() as conn:
            row = conn.execute(sql).mappings().first()
        return dict(row) if row else None

    def stats(self, episodes_total: int = 0) -> dict:
        last = self.last_run() or {}
        return {
            "episodes_discovered": int(last.get("episodes_discovered", 0) or 0),
            "transcripts_fetched": int(last.get("transcripts_fetched", 0) or 0),
            "distilled": int(last.get("distilled", 0) or 0),
            "reprocessed": int(last.get("reprocessed", 0) or 0),
            "failures": int(last.get("failures", 0) or 0),
            "episodes_total": int(episodes_total),
            "last_run_date": str(last.get("run_date")) if last.get("run_date") else None,
            "last_run_status": last.get("status"),
            "last_heartbeat": (
                last.get("last_heartbeat").isoformat() if last.get("last_heartbeat") else None
            ),
        }
