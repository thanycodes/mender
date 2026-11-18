"""The ONLY module that calls Llama.

Keeping every model call behind this one door means one place to change providers, count
tokens (credits) and fake the model in tests.

The model writes extraction *rules*, never the data itself. We never trust its output:
1. `response_format` with a JSON schema asks the model for the exact shape we want.
2. Pydantic (`Rules`) checks it anyway, plus that it covers exactly the requested fields.
3. If it's still wrong, we retry once and show the model its mistake; then we fail cleanly.

Config comes from environment variables so the key never touches git or the browser:
LLAMA_API_KEY (required), LLAMA_BASE_URL and LLAMA_MODEL (optional overrides).
"""

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from app.rules import FieldSpec, Rules

# Meta's OpenAI-compatible endpoint; any OpenAI-style Llama host works via LLAMA_BASE_URL.
DEFAULT_BASE_URL = "https://api.llama.com/compat/v1"
DEFAULT_MODEL = "Llama-4-Maverick-17B-128E-Instruct-FP8"
MAX_ATTEMPTS = 2
TIMEOUT_SECONDS = 60.0

SYSTEM_PROMPT = """You write CSS-selector extraction rules for a web scraper.
You are given simplified HTML from one page and the fields the user wants from each repeated item.
Return rules, not data:
- row_selector: a CSS selector matching every repeated item (one per row), and nothing else.
- For each field, a selector evaluated INSIDE one row element, and the requested type:
  text = the element's text; number = numeric text like a price;
  exists = true if the element is present.
- Prefer stable, meaningful classes, ids and data-* attributes. Avoid :nth-child and long chains.
- If every value of a text field starts with the same label (e.g. "by "), set strip_prefix to it.
- The HTML may say "N more similar elements omitted"; row_selector must match those too.
Answer only with JSON matching the given schema."""


class LLMError(Exception):
    """The model call failed or kept returning unusable rules. Callers mark the job failed."""


@dataclass(frozen=True)
class RulesResult:
    rules: Rules
    attempts: int
    tokens_used: int  # Tracked per call: the credit budget is a design goal (plan section 18).


def rules_schema(fields: list[FieldSpec]) -> dict[str, Any]:
    """A JSON schema pinned to *these* fields, so the model can't rename, drop or invent any."""
    field_schemas = {
        f.name: {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "type": {"type": "string", "enum": [f.type]},
                "strip_prefix": {"type": "string"},
            },
            "required": ["selector", "type"],
            "additionalProperties": False,
        }
        for f in fields
    }
    return {
        "type": "object",
        "properties": {
            "row_selector": {"type": "string"},
            "fields": {
                "type": "object",
                "properties": field_schemas,
                "required": [f.name for f in fields],
                "additionalProperties": False,
            },
        },
        "required": ["row_selector", "fields"],
        "additionalProperties": False,
    }


def parse_rules(content: str, fields: list[FieldSpec]) -> Rules:
    """Validate raw model output. Raises ValueError with a message we can show the model."""
    try:
        rules = Rules.model_validate_json(content)
    except ValidationError as exc:
        raise ValueError(f"Output did not match the rules schema: {exc}") from exc
    wanted = {f.name: f.type for f in fields}
    got = {name: rule.type for name, rule in rules.fields.items()}
    if got != wanted:
        raise ValueError(f"Fields must be exactly {wanted}, got {got}")
    if not rules.row_selector.strip() or any(not r.selector.strip() for r in rules.fields.values()):
        raise ValueError("Selectors must not be empty")
    return rules


def _user_prompt(html: str, fields: list[FieldSpec]) -> str:
    lines = []
    for f in fields:
        hint = f": {f.description}" if f.description else ""
        lines.append(f"- {f.name} ({f.type}){hint}")
    fields_text = "\n".join(lines)
    return f"Fields to extract from each item:\n{fields_text}\n\nSimplified HTML:\n{html}"


def _client() -> httpx.Client:
    api_key = os.environ.get("LLAMA_API_KEY")
    if not api_key:
        raise LLMError("LLAMA_API_KEY is not set")
    return httpx.Client(
        base_url=os.environ.get("LLAMA_BASE_URL", DEFAULT_BASE_URL),
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=TIMEOUT_SECONDS,
    )


def generate_rules(
    html: str, fields: list[FieldSpec], *, client: httpx.Client | None = None
) -> RulesResult:
    """Ask Llama for rules for `fields` on this (already shrunk) page.

    Slow (seconds) and costs credits, so only workers call this, at setup and for repairs.
    Pass `client` to inject a fake transport in tests.
    """
    if not fields:
        raise LLMError("At least one field is required")
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(html, fields)},
    ]
    body = {
        "model": os.environ.get("LLAMA_MODEL", DEFAULT_MODEL),
        "temperature": 0,  # Same page in, same rules out: easier to debug and to evaluate.
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "extraction_rules", "schema": rules_schema(fields)},
        },
    }
    tokens = 0
    owns_client = client is None
    http = client or _client()
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = http.post("/chat/completions", json={**body, "messages": messages})
                response.raise_for_status()
                payload = response.json()
                content = payload["choices"][0]["message"]["content"] or ""
            except httpx.HTTPError as exc:
                # Network/HTTP failures aren't the model's fault; Phase 3 workers retry these.
                raise LLMError(f"Llama request failed: {exc}") from exc
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                raise LLMError(f"Unexpected response shape from Llama: {exc}") from exc
            tokens += int((payload.get("usage") or {}).get("total_tokens") or 0)
            try:
                rules = parse_rules(content, fields)
            except ValueError as exc:
                if attempt == MAX_ATTEMPTS:
                    raise LLMError(f"No valid rules after {attempt} attempts: {exc}") from exc
                # Show the model its own answer and what was wrong, then ask once more.
                messages += [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": f"That was invalid: {exc}. Return corrected JSON."},
                ]
                continue
            return RulesResult(rules=rules, attempts=attempt, tokens_used=tokens)
    finally:
        if owns_client:
            http.close()
    raise AssertionError("unreachable")
