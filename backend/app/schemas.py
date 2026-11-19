"""The API's request and response shapes (its public contract with the web app).

Kept separate from the database models on purpose: tables can change without breaking
clients, and we never accidentally leak a column just because it exists.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.models import Job
from app.rules import FieldSpec

Schedule = Literal["manual", "hourly", "daily"]


class JobOut(BaseModel):
    id: int
    url: str
    status: str
    fields: list[FieldSpec]
    schedule: Schedule | None
    created_at: datetime

    @classmethod
    def of(cls, job: Job) -> "JobOut":
        return cls(
            id=job.id,
            url=job.url,
            status=job.status,
            fields=[FieldSpec.model_validate(f) for f in job.field_schema],
            schedule=job.schedule,
            created_at=job.created_at,
        )


class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    data: dict[str, Any]
    created_at: datetime


class RecordPage(BaseModel):
    total: int
    items: list[RecordOut]
