"""referenced entities (LLM pass 3)

Revision ID: 0003_referenced_entities
Revises: 0002_distillation_symbols
Create Date: 2026-08-03 12:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0003_referenced_entities"
down_revision = "0002_distillation_symbols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS allin.referenced_entities (
            id               BIGSERIAL PRIMARY KEY,
            episode_id       BIGINT NOT NULL REFERENCES allin.episodes(id) ON DELETE CASCADE,
            raw_mention      TEXT NOT NULL,
            entity_type      TEXT NOT NULL,
            company_name     TEXT,
            ticker           TEXT,
            speaker          TEXT,
            direction        TEXT,
            confidence       DOUBLE PRECISION,
            context          TEXT,
            model            TEXT NOT NULL,
            prompt_version   TEXT NOT NULL,
            idempotency_key  TEXT NOT NULL UNIQUE,
            watchlist_status TEXT NOT NULL DEFAULT 'pending',
            submitted_at     TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_allin_entities_episode "
        "ON allin.referenced_entities (episode_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_allin_entities_watchlist "
        "ON allin.referenced_entities (watchlist_status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_allin_entities_ticker "
        "ON allin.referenced_entities (ticker)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS allin.referenced_entities")
