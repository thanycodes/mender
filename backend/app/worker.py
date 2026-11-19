"""The worker: the only process that does slow work (fetching pages, calling Llama).

    uv run --env-file ../.env python -m app.worker

The API never waits on slow work. It writes "please do X" into Postgres and answers at once;
this loop picks the work up. Two kinds of work for now:
  1. Draft jobs without rules → ask Llama, save rule version 1 + a preview (not active yet).
  2. Jobs whose "Run now" was clicked → apply the active rules, save the rows.

Claiming uses `SELECT … FOR UPDATE SKIP LOCKED`: each worker locks the row it takes, and other
workers skip locked rows, so you can run several workers without two doing the same job.
Phase 3 replaces this polling with a Redis queue (RQ) plus a scheduler; the tasks stay the same.
"""

import logging
import time

import httpx
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.fetch import FetchError
from app.llm import LLMError
from app.models import Job, RuleVersion
from app.rules import FieldSpec
from app.tasks.generate_rules import generate_preview
from app.tasks.run_job import NoActiveRules, run_job

log = logging.getLogger("mender.worker")
IDLE_SLEEP_SECONDS = 1.0


def _claim(db: Session, *conditions) -> Job | None:
    return db.scalar(
        select(Job).where(*conditions).order_by(Job.id).limit(1).with_for_update(skip_locked=True)
    )


def generate_next(db: Session, *, llm_client: httpx.Client | None = None) -> bool:
    """Write rules for one waiting draft job. Returns False if there was nothing to do."""
    job = _claim(
        db,
        Job.status == "draft",
        Job.error.is_(None),
        ~exists().where(RuleVersion.job_id == Job.id),
    )
    if job is None:
        db.rollback()
        return False
    log.info("generating rules for job %s", job.id)
    fields = [FieldSpec.model_validate(f) for f in job.field_schema]
    try:
        preview = generate_preview(job.url, fields, llm_client=llm_client)
    except (FetchError, LLMError) as exc:
        job.error = str(exc)  # Shown on the preview page; the user can fix the input and retry.
        log.warning("job %s: %s", job.id, exc)
    except Exception:
        # A bug, not bad input. Mark the job failed so we don't retry it every second forever.
        log.exception("job %s: unexpected error", job.id)
        job.error = "Internal error while generating rules"
    else:
        job.versions.append(
            RuleVersion(
                version_no=1,
                rules=preview.rules.model_dump(exclude_none=True),
                created_by="llm",
                active=False,  # Only the user's Approve makes rules live.
                tokens_used=preview.tokens_used,
                preview={
                    "row_count": preview.row_count,
                    "rows": preview.rows,
                    "warnings": preview.warnings,
                },
            )
        )
    db.commit()
    return True


def run_next(db: Session) -> bool:
    """Handle one "Run now" request. Returns False if there was nothing to do."""
    job = _claim(db, Job.run_requested_at.is_not(None))
    if job is None:
        db.rollback()
        return False
    log.info("running job %s", job.id)
    # Cleared in the same transaction that saves the run: if we crash first, it's retried.
    job.run_requested_at = None
    try:
        run = run_job(db, job.id)
    except NoActiveRules:
        db.commit()  # Nothing to run (e.g. paused after the click); just drop the request.
        return True
    log.info("job %s run %s: %s, %s rows", job.id, run.id, run.health, run.row_count)
    return True


def work_once(db: Session, **kwargs) -> bool:
    return generate_next(db, **kwargs) or run_next(db)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    log.info("worker started")
    while True:
        try:
            with SessionLocal() as db:
                did_work = work_once(db)
        except Exception:
            # One bad job must not kill the worker; log it and keep serving others.
            log.exception("task failed")
            did_work = False
        if not did_work:
            time.sleep(IDLE_SLEEP_SECONDS)


if __name__ == "__main__":
    main()
