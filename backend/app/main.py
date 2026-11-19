"""The API server: Mender's one controlled entry point.

Rule: the API only does fast work (read the DB, write a row, queue a task).
Anything slow (fetching pages, calling Llama) belongs in a worker.
"""

import os
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Job, Record
from app.schemas import JobOut, RecordOut, RecordPage

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
