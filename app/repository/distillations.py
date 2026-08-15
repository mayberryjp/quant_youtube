from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.models.domain import Distillation

_COLUMNS = (
    "id, episode_id, model, prompt_version, summary, key_topics, "
    "segments, token_usage, request_payload, response_payload, request_id, is_current, created_at"
)


def _loads(value, default):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    return json.loads(value)


def _row_to_distillation(row: dict) -> Distillation:
    data = dict(row)
    data["key_topics"] = _loads(data.get("key_topics"), [])
    data["segments"] = _loads(data.get("segments"), [])
    data["token_usage"] = _loads(data.get("token_usage"), None)
    data["request_payload"] = _loads(data.get("request_payload"), {})
    data["response_payload"] = _loads(data.get("response_payload"), {})
    return Distillation.model_validate(data)


class DistillationRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def upsert(self, d: Distillation) -> Distillation:
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE allin.distillations SET is_current = false WHERE episode_id = :eid"),
                {"eid": d.episode_id},
            )
            row = conn.execute(
                text(
                    """
                    INSERT INTO allin.distillations
                        (episode_id, model, prompt_version, summary, key_topics, segments, token_usage,
                         request_payload, response_payload, request_id, is_current)
                    VALUES
                        (:episode_id, :model, :prompt_version, :summary, :key_topics, :segments, :token_usage,
                         :request_payload, :response_payload, :request_id, true)
                    ON CONFLICT (episode_id, model, prompt_version) DO UPDATE SET
                        summary = excluded.summary,
                        key_topics = excluded.key_topics,
                        segments = excluded.segments,
                        token_usage = excluded.token_usage,
                        request_payload = excluded.request_payload,
                        response_payload = excluded.response_payload,
                        request_id = excluded.request_id,
                        is_current = true,
                        created_at = CURRENT_TIMESTAMP
                    RETURNING id, episode_id, model, prompt_version, summary, key_topics, segments,
                              token_usage, request_payload, response_payload, request_id, is_current, created_at
                    """
                ),
                {
                    "episode_id": d.episode_id,
                    "model": d.model,
                    "prompt_version": d.prompt_version,
                    "summary": d.summary,
                    "key_topics": json.dumps(d.key_topics),
                    "segments": json.dumps(d.segments),
                    "token_usage": json.dumps(d.token_usage) if d.token_usage is not None else None,
                    "request_payload": json.dumps(d.request_payload),
                    "response_payload": json.dumps(d.response_payload),
                    "request_id": d.request_id,
                },
            ).mappings().first()
        return _row_to_distillation(row)

    def get_current(self, episode_id: int) -> Distillation | None:
        sql = text(
            f"SELECT {_COLUMNS} FROM allin.distillations WHERE episode_id = :eid AND is_current"
        )
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"eid": episode_id}).mappings().first()
        return _row_to_distillation(row) if row else None

    def get_current_map(self, episode_ids: list[int]) -> dict[int, Distillation]:
        if not episode_ids:
            return {}
        sql = text(
            f"SELECT {_COLUMNS} FROM allin.distillations WHERE is_current AND episode_id = ANY(:ids)"
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"ids": list(episode_ids)}).mappings().all()
        return {row["episode_id"]: _row_to_distillation(row) for row in rows}
