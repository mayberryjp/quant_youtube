"""make episode content hash index non-unique

Revision ID: 0004_content_hash_not_unique
Revises: 0003_referenced_entities
Create Date: 2026-08-10 09:20:00
"""

from __future__ import annotations

from alembic import op

revision = "0004_content_hash_not_unique"
down_revision = "0003_referenced_entities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS allin.uq_allin_episode_content_hash")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_allin_episode_content_hash "
        "ON allin.episodes(content_hash) WHERE content_hash IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS allin.ix_allin_episode_content_hash")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_allin_episode_content_hash "
        "ON allin.episodes(content_hash) WHERE content_hash IS NOT NULL"
    )
