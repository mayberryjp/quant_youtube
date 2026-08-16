from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.models.domain import Episode, EpisodeStatus

_COLUMNS = (
    "id, video_id, channel_slug, title, published_at, source_url, thumbnail_url, description, "
    "duration_seconds, transcript_language, transcript_source, content_hash, status, attempts, "
    "last_error, distill_job_id, discovered_at, fetched_at, distilled_at"
)


def _row_to_episode(row: dict, *, raw_text: str | None = None) -> Episode:
    data = dict(row)
    if raw_text is not None:
        data["raw_text"] = raw_text
    return Episode.model_validate(data)


class EpisodeRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def upsert_discovered(self, items: list[dict]) -> int:
        if not items:
            return 0
        sql = text(
            """
            INSERT INTO allin.episodes
                (video_id, channel_slug, title, published_at, source_url,
                 thumbnail_url, description, duration_seconds, status)
            VALUES
                (:video_id, :channel_slug, :title, :published_at, :source_url,
                 :thumbnail_url, :description, :duration_seconds, 'discovered')
            ON CONFLICT (video_id) DO NOTHING
            """
        )
        inserted = 0
        with self.engine.begin() as conn:
            for it in items:
                inserted += conn.execute(sql, it).rowcount or 0
        return inserted

    def get_by_identifier(self, video_id: str) -> Episode | None:
        sql = text(f"SELECT {_COLUMNS}, raw_text FROM allin.episodes WHERE video_id = :vid")
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"vid": video_id}).mappings().first()
        return _row_to_episode(row) if row else None

    def get_by_id(self, episode_id: int) -> Episode | None:
        sql = text(
            f"SELECT {_COLUMNS}, raw_text FROM allin.episodes WHERE id = :id"
        )
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"id": episode_id}).mappings().first()
        return _row_to_episode(row) if row else None

    def mark_fetched(
        self,
        episode_id: int,
        *,
        raw_text: str,
        content_hash: str,
        transcript_language: str | None = None,
        transcript_source: str | None = None,
        duration_seconds: int | None = None,
    ) -> None:
        sql = text(
            """
            UPDATE allin.episodes
            SET raw_text = :raw_text,
                content_hash = :content_hash,
                transcript_language = :transcript_language,
                transcript_source = :transcript_source,
                duration_seconds = COALESCE(:duration_seconds, duration_seconds),
                status = 'fetched',
                fetched_at = :now,
                last_error = NULL
            WHERE id = :id
            """
        )
        with self.engine.begin() as conn:
            conn.execute(
                sql,
                {
                    "id": episode_id,
                    "raw_text": raw_text,
                    "content_hash": content_hash,
                    "transcript_language": transcript_language,
                    "transcript_source": transcript_source,
                    "duration_seconds": duration_seconds,
                    "now": datetime.now(timezone.utc),
                },
            )

    def mark_skipped(
        self,
        episode_id: int,
        *,
        duration_seconds: int | None = None,
        reason: str | None = None,
    ) -> None:
        sql = text(
            """
            UPDATE allin.episodes
            SET status = 'skipped',
                duration_seconds = COALESCE(:duration_seconds, duration_seconds),
                last_error = :reason
            WHERE id = :id
            """
        )
        with self.engine.begin() as conn:
            conn.execute(
                sql,
                {
                    "id": episode_id,
                    "duration_seconds": duration_seconds,
                    "reason": reason,
                },
            )

    def set_status(
        self,
        episode_id: int,
        status: EpisodeStatus | str,
        *,
        last_error: str | None = None,
        bump_attempts: bool = False,
    ) -> None:
        status_val = status.value if isinstance(status, EpisodeStatus) else status
        sql = text(
            """
            UPDATE allin.episodes
            SET status = :status,
                last_error = :last_error,
                attempts = attempts + :attempt_bump
            WHERE id = :id
            """
        )
        with self.engine.begin() as conn:
            conn.execute(
                sql,
                {
                    "id": episode_id,
                    "status": status_val,
                    "last_error": last_error,
                    "attempt_bump": 1 if bump_attempts else 0,
                },
            )

    def set_distill_job(self, episode_id: int, job_id: str | None) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE allin.episodes SET distill_job_id = :job_id WHERE id = :id"),
                {"id": episode_id, "job_id": job_id},
            )

    def touch_stage(self, episode_id: int, stage: str) -> None:
        column = {"distilled": "distilled_at"}[stage]
        with self.engine.begin() as conn:
            conn.execute(
                text(f"UPDATE allin.episodes SET {column} = :now WHERE id = :id"),
                {"id": episode_id, "now": datetime.now(timezone.utc)},
            )

    def reset_for_reprocess(self, episode_id: int) -> bool:
        sql = text(
            """
            UPDATE allin.episodes
            SET status = 'fetched',
                last_error = NULL,
                distill_job_id = NULL
            WHERE id = :id AND raw_text IS NOT NULL
            """
        )
        with self.engine.begin() as conn:
            return (conn.execute(sql, {"id": episode_id}).rowcount or 0) > 0

    def reset_full(self, episode_id: int) -> bool:
        sql = text(
            """
            UPDATE allin.episodes
            SET status = 'discovered',
                raw_text = NULL,
                content_hash = NULL,
                transcript_language = NULL,
                transcript_source = NULL,
                last_error = NULL,
                distill_job_id = NULL,
                fetched_at = NULL,
                distilled_at = NULL
            WHERE id = :id
            """
        )
        with self.engine.begin() as conn:
            return (conn.execute(sql, {"id": episode_id}).rowcount or 0) > 0

    def delete(self, episode_id: int) -> bool:
        with self.engine.begin() as conn:
            return (conn.execute(text("DELETE FROM allin.episodes WHERE id = :id"), {"id": episode_id}).rowcount or 0) > 0

    def list_needing_transcript(self, *, limit: int = 200, max_attempts: int = 5) -> list[Episode]:
        """Episodes with no transcript yet: freshly discovered or a retryable failure."""
        sql = text(
            f"""
            SELECT {_COLUMNS}, raw_text FROM allin.episodes
             WHERE status = 'discovered'
                OR (status = 'failed' AND raw_text IS NULL AND attempts < :max_attempts)
             ORDER BY published_at DESC NULLS LAST, id DESC
             LIMIT :limit
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"max_attempts": max_attempts, "limit": limit}).mappings().all()
        return [_row_to_episode(r) for r in rows]

    def list_needing_distill(self, *, limit: int = 200, max_attempts: int = 5) -> list[Episode]:
        """Episodes with a transcript but no current distillation, plus retryable distill failures."""
        sql = text(
            f"""
            SELECT {_COLUMNS}, raw_text FROM allin.episodes
             WHERE status = 'fetched'
                OR (status = 'failed' AND raw_text IS NOT NULL AND attempts < :max_attempts)
             ORDER BY published_at DESC NULLS LAST, id DESC
             LIMIT :limit
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"max_attempts": max_attempts, "limit": limit}).mappings().all()
        return [_row_to_episode(r) for r in rows]

    def list(
        self,
        *,
        status: str | None = None,
        from_date=None,
        to_date=None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list[Episode], int]:
        clauses = []
        params: dict = {}
        if status:
            clauses.append("e.status = :status")
            params["status"] = status
        if from_date:
            clauses.append("date(e.published_at) >= :from_date")
            params["from_date"] = from_date
        if to_date:
            clauses.append("date(e.published_at) <= :to_date")
            params["to_date"] = to_date
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        offset = max(page - 1, 0) * page_size

        sql = text(
            f"""
            SELECT {_COLUMNS},
                   char_length(e.raw_text) AS raw_char_count,
                   d.summary_char_count,
                   d.key_topic_count,
                   d.segment_count
              FROM allin.episodes e
              LEFT JOIN (
                SELECT episode_id,
                       char_length(summary) AS summary_char_count,
                       COALESCE(jsonb_array_length(key_topics), 0) AS key_topic_count,
                       COALESCE(jsonb_array_length(segments), 0) AS segment_count
                  FROM allin.distillations
                 WHERE is_current
              ) d ON d.episode_id = e.id
              {where}
             ORDER BY e.published_at DESC NULLS LAST, e.id DESC
             LIMIT :limit OFFSET :offset
            """
        )
        count_sql = text(f"SELECT count(*) FROM allin.episodes e{where}")
        params_with_page = {**params, "limit": page_size, "offset": offset}
        with self.engine.connect() as conn:
            rows = conn.execute(sql, params_with_page).mappings().all()
            total = conn.execute(count_sql, params).scalar_one()
        return [_row_to_episode(r) for r in rows], int(total)

    def reprocess_candidates(
        self,
        *,
        from_date=None,
        to_date=None,
        only_stale: bool = False,
        current_model: str | None = None,
        current_prompt: str | None = None,
    ) -> list[Episode]:
        clauses = ["e.raw_text IS NOT NULL"]
        params: dict = {}
        if from_date:
            clauses.append("date(e.published_at) >= :from_date")
            params["from_date"] = from_date
        if to_date:
            clauses.append("date(e.published_at) <= :to_date")
            params["to_date"] = to_date
        if only_stale and current_model and current_prompt:
            clauses.append(
                "NOT EXISTS (SELECT 1 FROM allin.distillations d "
                "WHERE d.episode_id = e.id AND d.is_current "
                "AND d.model = :cur_model AND d.prompt_version = :cur_prompt)"
            )
            params["cur_model"] = current_model
            params["cur_prompt"] = current_prompt
        where = " WHERE " + " AND ".join(clauses)
        sql = text(f"SELECT {_COLUMNS}, raw_text FROM allin.episodes e{where} ORDER BY e.id")
        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [_row_to_episode(r) for r in rows]

    def failed_candidates(self, *, from_date=None, to_date=None, max_attempts: int | None = None) -> list[Episode]:
        clauses = ["status = 'failed'"]
        params: dict = {}
        if from_date:
            clauses.append("date(published_at) >= :from_date")
            params["from_date"] = from_date
        if to_date:
            clauses.append("date(published_at) <= :to_date")
            params["to_date"] = to_date
        if max_attempts is not None:
            clauses.append("attempts < :max_attempts")
            params["max_attempts"] = max_attempts
        where = " WHERE " + " AND ".join(clauses)
        sql = text(f"SELECT {_COLUMNS}, raw_text FROM allin.episodes{where} ORDER BY id")
        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [_row_to_episode(r) for r in rows]

    def count_total(self) -> int:
        with self.engine.connect() as conn:
            return int(conn.execute(text("SELECT count(*) FROM allin.episodes")).scalar_one())
