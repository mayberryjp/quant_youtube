"""track async distill job id on episodes

Revision ID: 0006_distill_job_id
Revises: 0005_shared_distill_api
Create Date: 2026-08-16 00:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0006_distill_job_id"
down_revision = "0005_shared_distill_api"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE allin.episodes ADD COLUMN IF NOT EXISTS distill_job_id TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE allin.episodes DROP COLUMN IF EXISTS distill_job_id")
