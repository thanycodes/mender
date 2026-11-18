from pathlib import Path

import httpx
import pytest

from app.fetch import USER_AGENT, FetchError, fetch_html

BOOKS = Path(__file__).resolve().parents[2] / "testsite" / "books" / "index.html"


def client_returning(status: int, text: str = "<html></html>") -> tuple[httpx.Client, list]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, text=text)

    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport, headers={"User-Agent": USER_AGENT}), seen


def test_fetches_http_page() -> None:
    client, seen = client_returning(200, "<p>hi</p>")

    assert fetch_html("https://shop.test/new", client=client) == "<p>hi</p>"
    assert seen[0].headers["User-Agent"].startswith("MenderBot")


def test_http_error_becomes_fetch_error() -> None:
    client, _ = client_returning(404)

    with pytest.raises(FetchError, match="404"):
        fetch_html("https://shop.test/missing", client=client)


def test_reads_local_test_page() -> None:
    assert "book-card" in fetch_html(str(BOOKS))
    assert "book-card" in fetch_html(f"file://{BOOKS}")


def test_missing_local_file() -> None:
    with pytest.raises(FetchError):
        fetch_html("/no/such/page.html")
