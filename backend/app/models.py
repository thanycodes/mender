"""Database tables (plan section 14). Postgres is the source of truth for all of these.

Flexible, per-job shapes (the field list, the rules, the extracted rows) live in JSONB columns;
everything we filter or join on is a real column with a constraint or index.
Users arrive with login in Phase 5; until then every job belongs to the single local owner.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JOB_STATUSES = ("draft", "active", "healing", "needs_human", "paused")
SCHEDULES = ("manual", "hourly", "daily")
RUN_HEALTH = ("ok", "broken", "error")  # error = fetch/infra failure, not a rules failure


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB}


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(_one_of("status", JOB_STATUSES), name="job_status_valid"),
        CheckConstraint(_one_of("schedule", SCHEDULES), name="job_schedule_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text)
    field_schema: Mapped[list[Any]]  # [{"name": "price", "type": "number", ...}] (FieldSpec)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    schedule: Mapped[str | None] = mapped_column(String(20))  # Set on approve.
    # Why rule generation failed, shown to the user. NULL while pending or after success.
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    versions: Mapped[list["RuleVersion"]] = relationship(
        back_populates="job", order_by="RuleVersion.version_no"
    )


class RuleVersion(Base):
    """Every set of rules a job ever had. Never updated in place: rollback = activate an old one."""

    __tablename__ = "rule_versions"
    __table_args__ = (
        UniqueConstraint("job_id", "version_no"),
        # At most one active version per job, enforced by the database itself.
        Index(
            "one_active_version_per_job",
            "job_id",
            unique=True,
            postgresql_where=text("active"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    version_no: Mapped[int]
    rules: Mapped[dict[str, Any]]
    created_by: Mapped[str] = mapped_column(String(20))  # "llm" | "human" (later "heal")
    active: Mapped[bool] = mapped_column(default=False)
    # Test-run result shown before approval: {"row_count", "rows", "warnings"}.
    preview: Mapped[dict[str, Any] | None]
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped[Job] = relationship(back_populates="versions")


class Run(Base):
    """One execution of a job's active rules."""

    __tablename__ = "runs"
    __table_args__ = (
        # A retried run for the same slot can't create a duplicate: idempotency in the schema.
        UniqueConstraint("job_id", "scheduled_for"),
        CheckConstraint(_one_of("health", RUN_HEALTH), name="run_health_valid"),
        Index("runs_job_started", "job_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    rule_version_id: Mapped[int | None] = mapped_column(ForeignKey("rule_versions.id"))
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_count: Mapped[int] = mapped_column(default=0)
    health: Mapped[str] = mapped_column(String(10))
    error: Mapped[str | None] = mapped_column(Text)

    records: Mapped[list["Record"]] = relationship(back_populates="run")


class Record(Base):
    """One extracted row. job_id is copied here so "latest rows for a job" needs no join."""

    __tablename__ = "records"
    __table_args__ = (Index("records_job_id", "job_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    data: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[Run] = relationship(back_populates="records")
