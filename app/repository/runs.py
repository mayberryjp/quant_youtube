from __future__ import annotations

import json
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.models.domain import IngestRun


def _loads(value, default):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    return json.loads(value)


def _row_to_run(row: dict) -> IngestRun:
    data = dict(row)
    data["notes"] = _loads(data.get("notes"), None)
    return IngestRun.model_validate(data)


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

    def get_by_run_date(self, run_date: date) -> IngestRun | None:
        sql = text("SELECT * FROM allin.ingest_runs WHERE run_date = :run_date")
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"run_date": run_date}).mappings().first()
        return _row_to_run(row) if row else None

    def list(
        self,
        *,
        status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list[IngestRun], int]:
        clauses = []
        params: dict = {}
        if status:
            clauses.append("status = :status")
            params["status"] = status
        if from_date:
            clauses.append("run_date >= :from_date")
            params["from_date"] = from_date
        if to_date:
            clauses.append("run_date <= :to_date")
            params["to_date"] = to_date
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        offset = max(page - 1, 0) * page_size
        sql = text(
            f"""
            SELECT * FROM allin.ingest_runs
             {where}
             ORDER BY run_date DESC
             LIMIT :limit OFFSET :offset
            """
        )
        count_sql = text(f"SELECT count(*) FROM allin.ingest_runs{where}")
        params_with_page = {**params, "limit": page_size, "offset": offset}
        with self.engine.connect() as conn:
            rows = conn.execute(sql, params_with_page).mappings().all()
            total = conn.execute(count_sql, params).scalar_one()
        return [_row_to_run(r) for r in rows], int(total)

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

    def totals(self) -> dict[str, int]:
        sql = text(
            """
            SELECT count(*) AS runs_total,
                   COALESCE(sum(episodes_discovered), 0) AS episodes_discovered,
                   COALESCE(sum(reprocessed), 0) AS reprocessed,
                   COALESCE(sum(failures), 0) AS failures
              FROM allin.ingest_runs
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(sql).mappings().one()
        return {key: int(value or 0) for key, value in row.items()}
