"""add symbols to distillations

Revision ID: 0002_distillation_symbols
Revises: 0001_allin_schema
Create Date: 2026-08-02 12:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0002_distillation_symbols"
down_revision = "0001_allin_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE allin.distillations
        ADD COLUMN IF NOT EXISTS symbols JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE allin.distillations
        DROP COLUMN IF EXISTS symbols
        """
    )
