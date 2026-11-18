"""Create rules for a new job: fetch → shrink → ask Llama → test-run → preview.

This is plan section 9, Scenario 1, steps 6–8. In Phase 3 a worker runs it from the queue
and saves the result as rule version 1 (inactive) for the user to approve. For now it's a
plain function, so the CLI and tests can call it directly.
"""

from dataclasses import dataclass, field

import httpx
from selectolax.lexbor import SelectolaxError

from app import llm
from app.fetch import fetch_html
from app.rules import FieldSpec, Rules
from app.tasks.extract import extract
from app.tasks.shrink import shrink_html

PREVIEW_ROWS = 10


@dataclass(frozen=True)
class Preview:
    rules: Rules
    row_count: int
    rows: list[dict]  # The first PREVIEW_ROWS rows, for the user to eyeball before approving.
    warnings: list[str] = field(default_factory=list)
    tokens_used: int = 0
    attempts: int = 0


def _test_run(html: str, rules: Rules) -> list[dict]:
    """Run rules on the FULL page. Raises ValueError so llm.py can feed problems back."""
    try:
        rows = extract(html, rules)
    except SelectolaxError as exc:
        raise ValueError(f"A selector is not valid CSS: {exc}") from exc
    if not rows:
        raise ValueError(f"row_selector {rules.row_selector!r} matched no elements on the page")
    return rows


def _warnings(rows: list[dict], fields: list[FieldSpec]) -> list[str]:
    """Things a human should look at, but that might be legitimate (e.g. everything sold out)."""
    found = []
    for f in fields:
        values = [row[f.name] for row in rows]
        if f.type == "exists":
            if len(set(values)) == 1:
                found.append(f"{f.name} is {values[0]} on every row")
        elif all(v is None for v in values):
            found.append(f"{f.name} is empty on every row")
        elif any(v is None for v in values):
            missing = sum(v is None for v in values)
            found.append(f"{f.name} is empty on {missing} of {len(values)} rows")
    return found


def generate_preview(
    url: str,
    fields: list[FieldSpec],
    *,
    llm_client: httpx.Client | None = None,
    fetch_client: httpx.Client | None = None,
) -> Preview:
    """Raises FetchError (page unreachable) or LLMError (no usable rules after retrying)."""
    html = fetch_html(url, client=fetch_client)

    def check(rules: Rules) -> None:
        _test_run(html, rules)

    result = llm.generate_rules(shrink_html(html), fields, check=check, client=llm_client)
    rows = _test_run(html, result.rules)
    return Preview(
        rules=result.rules,
        row_count=len(rows),
        rows=rows[:PREVIEW_ROWS],
        warnings=_warnings(rows, fields),
        tokens_used=result.tokens_used,
        attempts=result.attempts,
    )
