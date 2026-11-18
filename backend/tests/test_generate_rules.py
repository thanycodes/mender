"""End-to-end rule generation on the real test page, with a fake Llama."""

import json
from pathlib import Path

import httpx
import pytest

from app.cli import main, parse_field
from app.llm import LLMError
from app.tasks.generate_rules import generate_preview

BOOKS = Path(__file__).resolve().parents[2] / "testsite" / "books"
PAGE = str(BOOKS / "index.html")
GOOD = (BOOKS / "rules.v1.json").read_text()
FIELDS = [parse_field(f) for f in ["title", "author", "price:number", "in_stock:exists"]]
WRONG_ROWS = json.dumps(
    {**json.loads(GOOD), "row_selector": "div.does-not-exist"}  # Valid JSON, matches nothing.
)


def fake_llama(*contents: str) -> tuple[httpx.Client, list[dict]]:
    requests: list[dict] = []
    replies = iter(contents)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        message = {"role": "assistant", "content": next(replies)}
        return httpx.Response(200, json={"choices": [{"message": message}], "usage": {}})

    client = httpx.Client(base_url="https://llama.test", transport=httpx.MockTransport(handler))
    return client, requests


def test_preview_runs_rules_on_the_full_page() -> None:
    client, requests = fake_llama(GOOD)

    preview = generate_preview(PAGE, FIELDS, llm_client=client)

    assert preview.row_count == 12  # Llama saw 5 cards, but rules run on all 12.
    assert len(preview.rows) == 10
    assert preview.rows[0]["author"] == "Jane Doe"
    assert preview.warnings == []
    # The model was sent the shrunk page, not the original.
    prompt = requests[0]["messages"][1]["content"]
    assert "<script" not in prompt and "more similar elements omitted" in prompt


def test_zero_rows_is_fed_back_and_retried() -> None:
    client, requests = fake_llama(WRONG_ROWS, GOOD)

    preview = generate_preview(PAGE, FIELDS, llm_client=client)

    assert preview.attempts == 2
    assert "matched no elements" in requests[1]["messages"][-1]["content"]


def test_invalid_css_is_fed_back() -> None:
    bad_css = json.dumps({**json.loads(GOOD), "row_selector": "li[[["})
    client, requests = fake_llama(bad_css, GOOD)

    assert generate_preview(PAGE, FIELDS, llm_client=client).attempts == 2
    assert "not valid CSS" in requests[1]["messages"][-1]["content"]


def test_gives_up_after_two_bad_rule_sets() -> None:
    client, _ = fake_llama(WRONG_ROWS, WRONG_ROWS)

    with pytest.raises(LLMError, match="matched no elements"):
        generate_preview(PAGE, FIELDS, llm_client=client)


def test_warns_about_fields_that_look_wrong() -> None:
    rules = json.loads(GOOD)
    rules["fields"]["price"]["selector"] = "span.nope"
    client, _ = fake_llama(json.dumps(rules))

    preview = generate_preview(PAGE, FIELDS, llm_client=client)

    assert preview.warnings == ["price is empty on every row"]


def test_cli_reports_errors_without_a_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["/no/such/page.html", "title"]) == 1
    assert "error:" in capsys.readouterr().err


def test_parse_field() -> None:
    assert parse_field("price:number").type == "number"
    assert parse_field("title").type == "text"
    with pytest.raises(ValueError):
        parse_field("price:money")
