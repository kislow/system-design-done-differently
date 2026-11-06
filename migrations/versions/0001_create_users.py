"""create users table

Revision ID: 0001
Revises:
Create Date: 2026-11-05
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS because this baseline adopts a table the API used to create
    # on startup. On an existing volume it only records the version; on a fresh
    # one it creates the table.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL
        )
        """
    )


def downgrade() -> None:
    # downgrading to base deletes every user. That is what "before the first
    # migration" means, so it is deliberate, not a cleanup.
    op.execute("DROP TABLE users")
