"""Run a job once: fetch the page, apply the ACTIVE rules, save a Run and its Records.

This is the cheap, frequent path (no AI). The Run and all its Records are saved in ONE
transaction, so a crash halfway can never leave a run with half its rows.
UNIQUE(job_id, scheduled_for) makes it idempotent: running the same slot twice (e.g. a retry
after a crash) returns the existing run instead of saving duplicate rows.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.fetch import FetchError, fetch_html
from app.models import Job, Record, RuleVersion, Run
from app.rules import Rules
from app.tasks.extract import extract


class NoActiveRules(Exception):
    """The job has no approved rules yet, so there's nothing to run."""


def run_job(db: Session, job_id: int, scheduled_for: datetime | None = None) -> Run:
    now = datetime.now(UTC)
    slot = scheduled_for or now  # "Run now" gets its own slot; schedules (Phase 3) pass theirs.
    existing = db.scalar(select(Run).where(Run.job_id == job_id, Run.scheduled_for == slot))
    if existing:
        return existing

    job = db.get_one(Job, job_id)
    version = db.scalar(
        select(RuleVersion).where(RuleVersion.job_id == job.id, RuleVersion.active)
    )
    if version is None:
        raise NoActiveRules(f"Job {job.id} has no active rules")

    run = Run(job_id=job.id, rule_version_id=version.id, scheduled_for=slot, started_at=now)
    try:
        rows = extract(fetch_html(job.url), Rules.model_validate(version.rules))
    except FetchError as exc:
        run.health, run.error = "error", str(exc)  # The site was down: not the rules' fault.
        rows = []
    else:
        # Phase 1/2 health check: "0 rows" means the rules broke. Phase 4 adds the real
        # validator (row count vs. recent normal, empty fields, types) and the repair loop.
        run.health = "ok" if rows else "broken"
        if not rows:
            run.error = "Rules matched no rows"
    run.row_count = len(rows)
    run.finished_at = datetime.now(UTC)
    run.records = [Record(job_id=job.id, data=row) for row in rows]

    db.add(run)
    try:
        db.commit()  # Run + every Record, all or nothing.
    except IntegrityError:
        # Another worker saved this exact slot between our check and our commit.
        db.rollback()
        return db.scalars(
            select(Run).where(Run.job_id == job_id, Run.scheduled_for == slot)
        ).one()
    return run
