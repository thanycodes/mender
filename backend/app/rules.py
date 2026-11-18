"""Validate stored extraction rules before the worker applies them."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class FieldRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selector: str
    type: Literal["text", "number", "exists"]
    strip_prefix: str | None = None


class Rules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_selector: str
    fields: dict[str, FieldRule]
