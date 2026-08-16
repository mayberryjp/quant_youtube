"""track distill retry attempts separately from transcript attempts

Revision ID: 0007_distill_attempts
Revises: 0006_distill_job_id
Create Date: 2026-08-16 00:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0007_distill_attempts"
down_revision = "0006_distill_job_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE allin.episodes "
        "ADD COLUMN IF NOT EXISTS distill_attempts INTEGER NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE allin.episodes DROP COLUMN IF EXISTS distill_attempts")
