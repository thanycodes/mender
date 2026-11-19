"""The database enforces our rules itself, so a bug in app code can't corrupt the data."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Job, Record, RuleVersion, Run

RULES = {"row_selector": "li", "fields": {"title": {"selector": "h3", "type": "text"}}}


def make_job(db: Session) -> Job:
    job = Job(url="https://shop.test", field_schema=[{"name": "title", "type": "text"}])
    db.add(job)
    db.commit()
    return job


def test_job_defaults_to_draft(db: Session) -> None:
    job = make_job(db)

    assert job.status == "draft"
    assert job.created_at is not None


def test_status_must_be_known(db: Session) -> None:
    db.add(Job(url="https://shop.test", field_schema=[], status="exploded"))

    with pytest.raises(IntegrityError, match="job_status_valid"):
        db.commit()


def test_only_one_active_rule_version_per_job(db: Session) -> None:
    job = make_job(db)
    db.add(RuleVersion(job=job, version_no=1, rules=RULES, created_by="llm", active=True))
    db.add(RuleVersion(job=job, version_no=2, rules=RULES, created_by="llm", active=True))

    with pytest.raises(IntegrityError, match="one_active_version_per_job"):
        db.commit()


def test_retried_run_for_same_slot_is_rejected(db: Session) -> None:
    job = make_job(db)
    slot = datetime(2026, 11, 18, 7, tzinfo=UTC)
    for _ in range(2):
        db.add(Run(job_id=job.id, scheduled_for=slot, started_at=slot, health="ok"))

    with pytest.raises(IntegrityError, match="runs_job_id_scheduled_for_key"):
        db.commit()


def test_records_store_json_and_go_with_their_job(db: Session) -> None:
    job = make_job(db)
    now = datetime.now(UTC)
    run = Run(job_id=job.id, scheduled_for=now, started_at=now, health="ok", row_count=1)
    run.records.append(Record(job_id=job.id, data={"title": "A", "price": 18.99}))
    db.add(run)
    db.commit()
    assert db.get(Record, 1).data == {"title": "A", "price": 18.99}

    db.delete(job)
    db.commit()
    assert db.query(Record).count() == 0
