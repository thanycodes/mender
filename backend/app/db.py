"""Database connection. Postgres is Mender's source of truth.

One engine per process (it holds a pool of connections). Each request or task gets its own
short-lived Session, which is a unit of work: everything in it commits together or not at all.
"""

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_URL = "postgresql+psycopg://mender:mender@localhost:5432/mender"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


# pool_pre_ping: check a pooled connection is alive before using it (survives DB restarts).
engine = create_engine(database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed afterwards."""
    with SessionLocal() as session:
        yield session
