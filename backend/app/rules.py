"""Validate stored extraction rules before the worker applies them.

Rules are JSON *data*, not code. These models are the gate every set of rules must pass,
whether a human wrote it or Llama did.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FieldType = Literal["text", "number", "exists"]


class FieldRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selector: str
    type: FieldType
    strip_prefix: str | None = None


class Rules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_selector: str
    fields: dict[str, FieldRule]


class FieldSpec(BaseModel):
    """One field the user asked for ("price as a number"). Llama turns these into FieldRules."""

    model_config = ConfigDict(extra="forbid")

    # Snake-case names keep them safe as JSON keys, DB keys and table column headers.
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    type: FieldType = "text"
    description: str = Field(default="", max_length=200)
