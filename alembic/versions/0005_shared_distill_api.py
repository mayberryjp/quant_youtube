"""persist shared distillation API artifacts

Revision ID: 0005_shared_distill_api
Revises: 0004_content_hash_not_unique
Create Date: 2026-08-14 00:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0005_shared_distill_api"
down_revision = "0004_content_hash_not_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE allin.distillations ADD COLUMN IF NOT EXISTS request_payload JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE allin.distillations ADD COLUMN IF NOT EXISTS response_payload JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE allin.distillations ADD COLUMN IF NOT EXISTS request_id TEXT")
    op.execute("ALTER TABLE allin.distillations DROP COLUMN IF EXISTS symbols")
    op.execute("DROP TABLE IF EXISTS allin.referenced_entities")


def downgrade() -> None:
    op.execute("ALTER TABLE allin.distillations ADD COLUMN IF NOT EXISTS symbols JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS allin.referenced_entities (
            id BIGSERIAL PRIMARY KEY,
            episode_id BIGINT NOT NULL REFERENCES allin.episodes(id) ON DELETE CASCADE,
            raw_mention TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            company_name TEXT,
            ticker TEXT,
            speaker TEXT,
            direction TEXT,
            confidence DOUBLE PRECISION,
            context TEXT,
            model TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            watchlist_status TEXT NOT NULL DEFAULT 'pending',
            submitted_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("ALTER TABLE allin.distillations DROP COLUMN IF EXISTS request_id")
    op.execute("ALTER TABLE allin.distillations DROP COLUMN IF EXISTS response_payload")
    op.execute("ALTER TABLE allin.distillations DROP COLUMN IF EXISTS request_payload")
