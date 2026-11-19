"""Alembic runs migrations against DATABASE_URL using our models' metadata.

Migrations are how the database schema changes over time, in reviewed, versioned steps.
Never edit tables by hand: write a migration (`uv run alembic revision --autogenerate -m "…"`).
"""

from logging.config import fileConfig

from sqlalchemy import create_engine

from alembic import context
from app.db import database_url
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Print the SQL instead of running it (`alembic upgrade head --sql`)."""
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
