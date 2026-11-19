"""Phase 1 end to end: hand-written rules → run → rows in Postgres → API."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli import main
from app.db import get_session
from app.main import app
from app.models import Job, Record, Run
from app.tasks.run_job import NoActiveRules, run_job


@pytest.fixture
def books_job(db: Session) -> Job:
    assert main(["seed-books"]) == 0
    return db.scalars(select(Job)).one()


@pytest.fixture
def client(db: Session) -> TestClient:
    app.dependency_overrides[get_session] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_run_saves_run_and_records(db: Session, books_job: Job) -> None:
    run = run_job(db, books_job.id)

    assert (run.health, run.row_count) == ("ok", 12)
    assert db.query(Record).filter_by(run_id=run.id).count() == 12


def test_same_slot_twice_does_not_duplicate_rows(db: Session, books_job: Job) -> None:
    slot = datetime(2026, 11, 18, 7, tzinfo=UTC)

    first = run_job(db, books_job.id, scheduled_for=slot)
    second = run_job(db, books_job.id, scheduled_for=slot)

    assert first.id == second.id
    assert db.query(Record).count() == 12


def test_unreachable_page_is_an_error_not_broken(db: Session, books_job: Job) -> None:
    books_job.url = "/no/such/page.html"
    db.commit()

    run = run_job(db, books_job.id)

    assert (run.health, run.row_count) == ("error", 0)


def test_zero_rows_marks_the_run_broken(db: Session, books_job: Job) -> None:
    version = books_job.versions[0]
    version.rules = {**version.rules, "row_selector": "article.product"}  # "after a redesign"
    db.commit()

    run = run_job(db, books_job.id)

    assert run.health == "broken"
    assert db.query(Run).count() == 1


def test_job_without_active_rules(db: Session) -> None:
    job = Job(url="https://shop.test", field_schema=[])
    db.add(job)
    db.commit()

    with pytest.raises(NoActiveRules):
        run_job(db, job.id)


def test_api_lists_jobs_and_paginates_records(
    db: Session, books_job: Job, client: TestClient
) -> None:
    run_job(db, books_job.id)

    jobs = client.get("/jobs").json()
    assert [j["status"] for j in jobs] == ["active"]
    assert [f["name"] for f in jobs[0]["fields"]] == ["title", "author", "price", "in_stock"]

    page = client.get(f"/jobs/{books_job.id}/records", params={"limit": 5, "offset": 10}).json()
    assert page["total"] == 12
    assert len(page["items"]) == 2
    assert set(page["items"][0]["data"]) == {"title", "author", "price", "in_stock"}


def test_api_404_for_unknown_job(client: TestClient) -> None:
    assert client.get("/jobs/999").status_code == 404
    assert client.get("/jobs/999/records").status_code == 404
