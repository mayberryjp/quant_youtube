"""allin schema

Revision ID: 0001_allin_schema
Revises: 0000_baseline
Create Date: 2026-08-02 00:20:00
"""

from __future__ import annotations

from alembic import op

revision = "0001_allin_schema"
down_revision = "0000_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS allin")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS allin.episodes (
            id BIGSERIAL PRIMARY KEY,
            video_id TEXT NOT NULL UNIQUE,
            channel_slug TEXT NOT NULL DEFAULT 'allin',
            title TEXT,
            published_at TIMESTAMPTZ,
            source_url TEXT NOT NULL,
            thumbnail_url TEXT,
            description TEXT,
            duration_seconds INT,
            transcript_language TEXT,
            transcript_source TEXT,
            content_hash TEXT,
            raw_text TEXT,
            status TEXT NOT NULL DEFAULT 'discovered',
            attempts INT NOT NULL DEFAULT 0,
            last_error TEXT,
            discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            fetched_at TIMESTAMPTZ,
            distilled_at TIMESTAMPTZ
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS allin.distillations (
            id BIGSERIAL PRIMARY KEY,
            episode_id BIGINT NOT NULL REFERENCES allin.episodes(id) ON DELETE CASCADE,
            model TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            summary TEXT NOT NULL,
            key_topics JSONB NOT NULL DEFAULT '[]'::jsonb,
            segments JSONB NOT NULL DEFAULT '[]'::jsonb,
            token_usage JSONB,
            is_current BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (episode_id, model, prompt_version)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS allin.ingest_runs (
            run_date DATE PRIMARY KEY,
            status TEXT NOT NULL,
            episodes_discovered INT NOT NULL DEFAULT 0,
            transcripts_fetched INT NOT NULL DEFAULT 0,
            distilled INT NOT NULL DEFAULT 0,
            reprocessed INT NOT NULL DEFAULT 0,
            failures INT NOT NULL DEFAULT 0,
            last_heartbeat TIMESTAMPTZ,
            notes JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_allin_episode_content_hash ON allin.episodes(content_hash) WHERE content_hash IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_allin_episode_status_published ON allin.episodes(status, published_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_allin_episode_published ON allin.episodes(published_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS allin.ingest_runs")
    op.execute("DROP TABLE IF EXISTS allin.distillations")
    op.execute("DROP TABLE IF EXISTS allin.episodes")
    op.execute("DROP SCHEMA IF EXISTS allin")
