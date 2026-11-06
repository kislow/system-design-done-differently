"""add created_at to users

Revision ID: b05c19687254
Revises: 0002
Create Date: 2026-11-05 22:51:50.053121
"""
from alembic import op

revision = 'b05c19687254'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT now()")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN created_at")
