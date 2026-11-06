"""unique user email

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fails and rolls back if two rows already share an email, and Postgres
    # names the duplicated value. Fix those rows by hand first: which user keeps
    # the address is a business decision, not one a migration should guess.
    #
    # ADD CONSTRAINT holds an ACCESS EXCLUSIVE lock, blocking reads and writes,
    # while it builds the index. Fine at this size; on a large table, build the
    # index with CREATE UNIQUE INDEX CONCURRENTLY and attach it with USING INDEX.
    op.execute("ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE (email)")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT users_email_key")
