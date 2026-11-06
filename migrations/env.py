import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)

# The API hands this DSN straight to psycopg. SQLAlchemy needs the driver named
# in the scheme, or it falls back to psycopg2, which is not installed.
url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1)

if context.is_offline_mode():
    # `alembic upgrade head --sql` prints the SQL instead of running it, so a
    # migration can be reviewed before it touches a database.
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(url).connect() as connection:
        # one transaction per migration: Postgres DDL is transactional, so a
        # failed migration rolls back whole and leaves the version where it was.
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()
