"""Test doubles shared by several test files: a fake Llama server and the books page."""

import json
from pathlib import Path

import httpx

BOOKS = Path(__file__).resolve().parents[2] / "testsite" / "books"
BOOKS_HTML = (BOOKS / "index.html").read_text(encoding="utf-8")
GOOD_RULES = (BOOKS / "rules.v1.json").read_text(encoding="utf-8")


def fake_llama(*contents: str) -> tuple[httpx.Client, list[dict]]:
    """A Llama client whose server replies with `contents` in order; records request bodies."""
    requests: list[dict] = []
    replies = iter(contents)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        message = {"role": "assistant", "content": next(replies)}
        body = {"choices": [{"message": message}], "usage": {"total_tokens": 100}}
        return httpx.Response(200, json=body)

    client = httpx.Client(base_url="https://llama.test", transport=httpx.MockTransport(handler))
    return client, requests
