"""move all project tables into the youtube schema

Revision ID: 0008_youtube_schema
Revises: 0007_distill_attempts
Create Date: 2026-09-04 00:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0008_youtube_schema"
down_revision = "0007_distill_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS youtube")
    # Move every table still living in the old schema (with its data, indexes, and owned
    # sequences) into youtube, then drop the now-empty legacy schema. alembic_version was
    # already relocated in env.py, so it is not present here.
    op.execute(
        """
        DO $$
        DECLARE
            obj record;
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'allin') THEN
                FOR obj IN SELECT tablename FROM pg_tables WHERE schemaname = 'allin' LOOP
                    EXECUTE format('ALTER TABLE allin.%I SET SCHEMA youtube', obj.tablename);
                END LOOP;
                FOR obj IN SELECT sequencename FROM pg_sequences WHERE schemaname = 'allin' LOOP
                    EXECUTE format('ALTER SEQUENCE allin.%I SET SCHEMA youtube', obj.sequencename);
                END LOOP;
                DROP SCHEMA IF EXISTS allin CASCADE;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS allin")
    op.execute("ALTER TABLE IF EXISTS youtube.ingest_runs SET SCHEMA allin")
    op.execute("ALTER TABLE IF EXISTS youtube.distillations SET SCHEMA allin")
    op.execute("ALTER TABLE IF EXISTS youtube.episodes SET SCHEMA allin")
