"""Shared fixtures. Database tests use a separate `mender_test` database, never dev data.

Pure tests (extractor, shrinker, llm) don't touch these fixtures, so they run without Postgres.
"""

import os

# Must be set before app.db is imported anywhere, because the engine is created at import.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://mender:mender@localhost:5432/mender_test"
)

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.models import Base  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def migrated() -> None:
    """Build the schema with the real migrations, so tests also prove the migrations work."""
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture
def db(migrated: None) -> Iterator[Session]:
    """A session on an empty database. Tables are wiped after each test."""
    with SessionLocal() as session:
        yield session
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
