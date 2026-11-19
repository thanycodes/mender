"""Phase 2 end to end: describe data → worker asks (fake) Llama → preview → approve → run."""

import json
from collections.abc import Iterator

import pytest
from fakes import BOOKS_HTML, GOOD_RULES, fake_llama
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import get_session
from app.main import app
from app.tasks import generate_rules, run_job
from app.worker import generate_next, run_next, work_once

NEW_JOB = {
    "url": "https://books.test/new-releases",
    "fields": [
        {"name": "title", "type": "text"},
        {"name": "author", "type": "text"},
        {"name": "price", "type": "number"},
        {"name": "in_stock", "type": "exists", "description": "add-to-cart button shown"},
    ],
}


@pytest.fixture
def client(db: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # Pretend books.test serves our test page, so no test touches the real network.
    for module in (generate_rules, run_job):
        monkeypatch.setattr(module, "fetch_html", lambda url, **_: BOOKS_HTML)
    app.dependency_overrides[get_session] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def create(client: TestClient) -> int:
    response = client.post("/jobs", json=NEW_JOB)
    assert response.status_code == 202
    assert response.json()["status"] == "draft"
    return response.json()["job_id"]


def test_full_flow(client: TestClient, db: Session) -> None:
    job_id = create(client)
    assert client.get(f"/jobs/{job_id}/preview").json()["state"] == "pending"

    llama, _ = fake_llama(GOOD_RULES)
    assert generate_next(db, llm_client=llama)

    preview = client.get(f"/jobs/{job_id}/preview").json()
    assert preview["state"] == "ready"
    assert (preview["version_no"], preview["row_count"], len(preview["rows"])) == (1, 12, 10)
    assert preview["rules"]["row_selector"] == "ul.book-grid > li.book-card"
    assert client.get(f"/jobs/{job_id}/records").json()["total"] == 0  # Not approved yet.

    approved = client.post(f"/jobs/{job_id}/approve", json={"schedule": "daily"}).json()
    assert (approved["status"], approved["schedule"]) == ("active", "daily")
    assert client.post(f"/jobs/{job_id}/approve", json={"schedule": "daily"}).status_code == 409

    assert client.post(f"/jobs/{job_id}/run").status_code == 202
    assert run_next(db)
    assert not run_next(db)  # The request was consumed.
    assert client.get(f"/jobs/{job_id}/records").json()["total"] == 12


def test_failed_generation_can_be_retried(client: TestClient, db: Session) -> None:
    job_id = create(client)
    llama, _ = fake_llama("{}", "{}")

    assert generate_next(db, llm_client=llama)
    failed = client.get(f"/jobs/{job_id}/preview").json()
    assert failed["state"] == "failed"
    assert "after 2 attempts" in failed["error"]
    assert not generate_next(db)  # A failed job isn't picked up again by itself.

    assert client.post(f"/jobs/{job_id}/retry").status_code == 202
    assert client.get(f"/jobs/{job_id}/preview").json()["state"] == "pending"
    llama, _ = fake_llama(GOOD_RULES)
    assert generate_next(db, llm_client=llama)
    assert client.get(f"/jobs/{job_id}/preview").json()["state"] == "ready"


def test_field_descriptions_reach_the_prompt(client: TestClient, db: Session) -> None:
    create(client)
    llama, requests = fake_llama(GOOD_RULES)

    generate_next(db, llm_client=llama)

    assert "in_stock (exists): add-to-cart button shown" in requests[0]["messages"][1]["content"]


def test_cannot_approve_or_run_too_early(client: TestClient) -> None:
    job_id = create(client)

    assert client.post(f"/jobs/{job_id}/approve", json={"schedule": "daily"}).status_code == 409
    assert client.post(f"/jobs/{job_id}/run").status_code == 409


@pytest.mark.parametrize(
    "change",
    [
        {"url": "/etc/passwd"},  # Local paths would let callers read server files.
        {"url": "file:///etc/passwd"},
        {"fields": []},
        {"fields": [{"name": "title"}, {"name": "title"}]},
        {"fields": [{"name": "Bad Name"}]},
        {"schedule": "daily"},  # Unknown keys are rejected, not silently ignored.
    ],
)
def test_create_rejects_bad_input(client: TestClient, change: dict) -> None:
    response = client.post("/jobs", json={**NEW_JOB, **change})

    assert response.status_code == 422, json.dumps(response.json())


def test_worker_with_nothing_to_do(db: Session) -> None:
    assert work_once(db) is False
