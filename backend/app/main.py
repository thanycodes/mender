"""The API server: Mender's one controlled entry point.

Rule: the API only does fast work (read the DB, write a row, queue a task).
Anything slow (fetching pages, calling Llama) belongs in a worker.
"""

import os
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Job, Record, RuleVersion
from app.schemas import (
    Approve,
    JobCreate,
    JobCreated,
    JobOut,
    Preview,
    RecordOut,
    RecordPage,
    RunQueued,
)

app = FastAPI(title="Mender API", version="0.1.0")

# The browser blocks calls from the web app (port 3000) to the API (port 8000) unless the API
# says that origin is allowed. List exact origins; never "*" once there are logins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

DB = Annotated[Session, Depends(get_session)]


def get_job(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, f"Job {job_id} not found")
    return job


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check. Used by humans, CI, and later by Docker/hosting health probes."""
    return {"status": "ok"}


@app.get("/jobs")
def list_jobs(db: DB) -> list[JobOut]:
    jobs = db.scalars(select(Job).order_by(Job.id.desc()))
    return [JobOut.of(job) for job in jobs]


@app.post("/jobs", status_code=202)
def create_job(body: JobCreate, db: DB) -> JobCreated:
    """Save a draft and return at once (202 = "accepted, still working on it").

    We don't call Llama here: that takes seconds. The worker sees the new draft and writes
    the rules; the web app polls GET /jobs/{id}/preview until they're ready.
    """
    job = Job(url=str(body.url), field_schema=[f.model_dump() for f in body.fields])
    db.add(job)
    db.commit()
    return JobCreated(job_id=job.id, status=job.status)


@app.get("/jobs/{job_id}")
def read_job(job_id: int, db: DB) -> JobOut:
    return JobOut.of(get_job(db, job_id))


@app.get("/jobs/{job_id}/records")
def list_records(
    job_id: int,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RecordPage:
    """Newest rows first. Paginated, because a daily job builds up thousands of rows."""
    get_job(db, job_id)
    total = db.scalar(select(func.count()).where(Record.job_id == job_id)) or 0
    records = db.scalars(
        select(Record)
        .where(Record.job_id == job_id)
        .order_by(Record.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return RecordPage(total=total, items=[RecordOut.model_validate(r) for r in records])


def latest_version(job: Job) -> RuleVersion | None:
    return job.versions[-1] if job.versions else None


@app.get("/jobs/{job_id}/preview")
def read_preview(job_id: int, db: DB) -> Preview:
    job = get_job(db, job_id)
    version = latest_version(job)
    if version is None:
        if job.error:
            return Preview(state="failed", error=job.error)
        return Preview(state="pending")
    preview = version.preview or {}
    return Preview(
        state="ready",
        version_no=version.version_no,
        rules=version.rules,
        row_count=preview.get("row_count", 0),
        rows=preview.get("rows", []),
        warnings=preview.get("warnings", []),
    )


@app.post("/jobs/{job_id}/retry", status_code=202)
def retry_generation(job_id: int, db: DB) -> JobCreated:
    """After a failed generation (site down, bad model answer), let the worker try again."""
    job = get_job(db, job_id)
    if job.status != "draft" or job.versions:
        raise HTTPException(409, "Only a draft whose rule generation failed can be retried")
    job.error = None
    db.commit()
    return JobCreated(job_id=job.id, status=job.status)


@app.post("/jobs/{job_id}/approve")
def approve(job_id: int, body: Approve, db: DB) -> JobOut:
    """The human says "these rules look right": activate them and set the schedule."""
    job = get_job(db, job_id)
    version = latest_version(job)
    if job.status != "draft" or version is None:
        raise HTTPException(409, "There are no generated rules waiting for approval")
    version.active = True
    job.status = "active"
    job.schedule = body.schedule
    db.commit()
    return JobOut.of(job)


@app.post("/jobs/{job_id}/run", status_code=202)
def request_run(job_id: int, db: DB) -> RunQueued:
    """Queue a run: fetching the page is slow, so the worker does it, not the API."""
    job = get_job(db, job_id)
    if job.status != "active":
        raise HTTPException(409, "Only an active job can be run")
    job.run_requested_at = datetime.now(UTC)
    db.commit()
    return RunQueued(job_id=job.id)
