"""Download a page's HTML. Workers call this; the API never does (it's slow network I/O).

Phase 2 uses plain HTTP. Phase 3 adds Playwright for pages that build their content with
JavaScript, behind this same function.
"""

from pathlib import Path

import httpx

TIMEOUT_SECONDS = 20.0
MAX_BYTES = 5_000_000  # A listing page bigger than this is almost certainly not what we want.
# An honest, identifiable client. We scrape politely (plan section 22), not stealthily.
USER_AGENT = "MenderBot/0.1 (+https://github.com/thanycodes/mender)"


class FetchError(Exception):
    """The page could not be fetched. This is an infra failure, not a broken-rules signal."""


def fetch_html(url: str, *, client: httpx.Client | None = None) -> str:
    """Return the page HTML for an http(s) URL, or a local file path (used for `testsite/`)."""
    if not url.startswith(("http://", "https://")):
        path = Path(url.removeprefix("file://"))
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise FetchError(f"Could not read {path}: {exc}") from exc

    http = client or httpx.Client(
        timeout=TIMEOUT_SECONDS, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    )
    try:
        response = http.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FetchError(f"Could not fetch {url}: {exc}") from exc
    finally:
        if client is None:
            http.close()
    if len(response.content) > MAX_BYTES:
        raise FetchError(f"Page is larger than {MAX_BYTES} bytes")
    return response.text
