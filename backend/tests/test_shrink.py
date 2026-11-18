from pathlib import Path

from selectolax.lexbor import LexborHTMLParser

from app.rules import Rules
from app.tasks.extract import extract
from app.tasks.shrink import shrink_html

BOOKS = Path(__file__).resolve().parents[2] / "testsite" / "books"


def test_keeps_selector_attributes_and_removes_unneeded_markup() -> None:
    html = """
        <html><head><title>Page title</title><meta charset="utf-8"><link href="/site.css"></head>
        <body>
          <script>script content</script><style>style content</style>
          <noscript>fallback content</noscript><svg><text>icon content</text></svg>
          <iframe>iframe content</iframe><template><b>template content</b></template>
          <!-- old comment -->
          <article class="book featured" id="book-1" data-sku="bk-1" itemprop="item"
                   role="article" aria-label="A &amp; B" style="color: red" onclick="openBook()">
            <a href="/books/1" title="A &quot;book&quot;">A &lt; B</a>
            <img src="/cover.jpg" alt="Cover">
            <input type="text" name="search" disabled>
          </article>
        </body></html>
    """

    shrunk = shrink_html(html)
    document = LexborHTMLParser(shrunk)

    assert shrunk.startswith("<article")
    assert shrunk.endswith("</article>")
    assert "content" not in shrunk
    assert "<!--" not in shrunk
    assert "Page title" not in shrunk
    assert not document.css("script, style, noscript, svg, iframe, template, link, meta")
    assert document.css_first("article").attributes == {
        "class": "book featured",
        "id": "book-1",
        "data-sku": "bk-1",
        "itemprop": "item",
        "role": "article",
        "aria-label": "A & B",
    }
    link = document.css_first("a")
    assert link.attributes == {"href": "/books/1", "title": 'A "book"'}
    assert link.text() == "A < B"
    assert document.css_first("img").attributes == {"src": "/cover.jpg", "alt": "Cover"}
    assert document.css_first("input").attributes == {"type": "text", "name": "search"}


def test_collapses_whitespace_and_shortens_long_values() -> None:
    href = "/" + "a" * 120
    src = "/" + "b" * 120
    text = "x" * 220
    html = f'<p>One \n <!-- comment --> <b>two</b>\t three</p><a href="{href}">{text}</a>'
    html += f'<img src="{src}">'

    shrunk = shrink_html(html)
    document = LexborHTMLParser(shrunk)

    assert "<p>One <b>two</b> three</p>" in shrunk
    assert document.css_first("a").attributes["href"] == href[:79] + "…"
    assert document.css_first("a").text() == text[:199] + "…"
    assert document.css_first("img").attributes["src"] == src[:79] + "…"


def test_keeps_first_five_of_each_sibling_group_at_every_level() -> None:
    cards = "".join(
        f'<article class="{classes}">Book {index}</article>'
        for index, classes in enumerate(["book card", "card  book"] * 6)
    )
    html = f'<main>{cards}<article class="promo">Sale</article></main><aside>{cards}</aside>'

    shrunk = shrink_html(html)
    document = LexborHTMLParser(shrunk)

    for parent in ("main", "aside"):
        assert [node.text() for node in document.css(f"{parent} > article.book")] == [
            f"Book {index}" for index in range(5)
        ]
    assert document.css_first("article.promo").text() == "Sale"
    assert shrunk.count("<!-- … 7 more similar elements omitted -->") == 2


def test_shrunk_books_page_preserves_extracted_values() -> None:
    html = (BOOKS / "index.html").read_text(encoding="utf-8")
    rules = Rules.model_validate_json((BOOKS / "rules.v1.json").read_bytes())
    original_records = extract(html, rules)

    shrunk = shrink_html(html)

    assert len(shrunk) < len(html) / 2
    assert len(original_records) == 12
    assert extract(shrunk, rules) == original_records[:5]
    assert "<!-- … 7 more similar elements omitted -->" in shrunk


def test_max_chars_truncates_and_appends_marker() -> None:
    html = "<p>New releases</p>"

    assert shrink_html(html, max_chars=6) == "<p>New<!-- truncated -->"
    assert shrink_html(html, max_chars=len(html)) == html


def test_handles_empty_html_and_documents_without_a_body() -> None:
    assert shrink_html("") == ""
    html = '<!doctype html><head><title>Frames</title></head><frameset><frame src="/"></frameset>'
    assert shrink_html(html) == '<!DOCTYPE html><html><frameset><frame src="/"></frameset></html>'
