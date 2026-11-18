"""Tests for the Llama client, with a fake HTTP transport: no network, no credits."""

import json

import httpx
import pytest

from app.llm import LLMError, generate_rules, parse_rules, rules_schema
from app.rules import FieldSpec

FIELDS = [FieldSpec(name="title"), FieldSpec(name="price", type="number")]
GOOD = {
    "row_selector": "li.book-card",
    "fields": {
        "title": {"selector": "h3.book-title", "type": "text"},
        "price": {"selector": "div.price-tag", "type": "number"},
    },
}


def fake_llama(*contents: str, status: int = 200) -> tuple[httpx.Client, list[dict]]:
    """A client whose server replies with `contents` in order and records each request body."""
    requests: list[dict] = []
    replies = iter(contents)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        body = {
            "choices": [{"message": {"role": "assistant", "content": next(replies, "")}}],
            "usage": {"total_tokens": 100},
        }
        return httpx.Response(status, json=body)

    client = httpx.Client(base_url="https://llama.test", transport=httpx.MockTransport(handler))
    return client, requests


def test_valid_rules_on_first_try() -> None:
    client, requests = fake_llama(json.dumps(GOOD))

    result = generate_rules("<ul>…</ul>", FIELDS, client=client)

    assert result.rules.row_selector == "li.book-card"
    assert result.attempts == 1
    assert result.tokens_used == 100
    sent = requests[0]
    assert sent["response_format"]["type"] == "json_schema"
    assert "price (number)" in sent["messages"][1]["content"]


def test_retries_once_with_the_error_then_succeeds() -> None:
    client, requests = fake_llama("not json at all", json.dumps(GOOD))

    result = generate_rules("<ul>…</ul>", FIELDS, client=client)

    assert result.attempts == 2
    assert result.tokens_used == 200
    retry_messages = requests[1]["messages"]
    assert retry_messages[2] == {"role": "assistant", "content": "not json at all"}
    assert "invalid" in retry_messages[3]["content"]


def test_fails_cleanly_after_two_bad_answers() -> None:
    client, requests = fake_llama("{}", "{}")

    with pytest.raises(LLMError, match="after 2 attempts"):
        generate_rules("<ul>…</ul>", FIELDS, client=client)
    assert len(requests) == 2


def test_http_error_is_not_retried() -> None:
    client, requests = fake_llama(json.dumps(GOOD), status=500)

    with pytest.raises(LLMError, match="request failed"):
        generate_rules("<ul>…</ul>", FIELDS, client=client)
    assert len(requests) == 1


def test_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLAMA_API_KEY", raising=False)

    with pytest.raises(LLMError, match="LLAMA_API_KEY"):
        generate_rules("<ul>…</ul>", FIELDS)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda r: r["fields"].pop("price"), "exactly"),
        (lambda r: r["fields"].update(isbn={"selector": "b", "type": "text"}), "exactly"),
        (lambda r: r["fields"]["price"].update(type="text"), "exactly"),
        (lambda r: r.update(row_selector="  "), "empty"),
        (lambda r: r.update(notes="hi"), "schema"),
    ],
)
def test_parse_rules_rejects_wrong_output(change, message: str) -> None:
    rules = json.loads(json.dumps(GOOD))
    change(rules)

    with pytest.raises(ValueError, match=message):
        parse_rules(json.dumps(rules), FIELDS)


def test_schema_pins_field_names_and_types() -> None:
    schema = rules_schema(FIELDS)["properties"]["fields"]

    assert schema["required"] == ["title", "price"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["price"]["properties"]["type"]["enum"] == ["number"]


def test_field_spec_rejects_unsafe_names() -> None:
    with pytest.raises(ValueError):
        FieldSpec(name="Price; DROP TABLE")
