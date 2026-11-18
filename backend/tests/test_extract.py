from pathlib import Path

import pytest
from pydantic import ValidationError

from app.rules import FieldRule, Rules
from app.tasks.extract import extract

BOOKS = Path(__file__).resolve().parents[2] / "testsite" / "books"


def test_extract_book_releases() -> None:
    html = (BOOKS / "index.html").read_text(encoding="utf-8")
    rules = Rules.model_validate_json((BOOKS / "rules.v1.json").read_bytes())

    records = extract(html, rules)

    assert len(records) == 12
    books = {record["title"]: record for record in records}
    assert books["The Quiet River"] == {
        "title": "The Quiet River",
        "author": "Jane Doe",
        "price": 18.99,
        "in_stock": True,
    }
    assert books["The Last Ferry Home"]["in_stock"] is False
    assert books["Atlas of Vanishing Islands"]["price"] == 1299.0


def test_no_matching_rows() -> None:
    rules = Rules(row_selector=".book", fields={"title": FieldRule(selector="h3", type="text")})

    assert extract("<article><h3>A book</h3></article>", rules) == []


def test_missing_field() -> None:
    rules = Rules(row_selector="article", fields={"title": FieldRule(selector="h3", type="text")})

    assert extract("<article></article><h3>Outside the row</h3>", rules) == [{"title": None}]


def test_field_selector_matches_only_descendants() -> None:
    rules = Rules(
        row_selector="article", fields={"title": FieldRule(selector=".title", type="text")}
    )
    html = """
        <article class="title">Row text</article>
        <article class="title"><h3 class="title">Book title</h3></article>
    """

    assert extract(html, rules) == [{"title": None}, {"title": "Book title"}]


def test_unparseable_number() -> None:
    rules = Rules(row_selector="article", fields={"price": FieldRule(selector="p", type="number")})

    assert extract("<article><p>Contact for price</p></article>", rules) == [{"price": None}]


def test_text_collapses_whitespace_before_removing_prefix() -> None:
    rules = Rules(
        row_selector="article",
        fields={"author": FieldRule(selector="span", type="text", strip_prefix="by ")},
    )

    assert extract("<article><span>\n by\t Jane   Doe </span></article>", rules) == [
        {"author": "Jane Doe"}
    ]


@pytest.mark.parametrize(
    ("payload", "location", "error_type"),
    [
        (
            {"row_selector": "li", "fields": {"title": {"selector": "h3", "type": "html"}}},
            ("fields", "title", "type"),
            "literal_error",
        ),
        (
            {
                "row_selector": "li",
                "fields": {"title": {"selector": "h3", "type": "text", "default": "Untitled"}},
            },
            ("fields", "title", "default"),
            "extra_forbidden",
        ),
        ({"row_selector": "li", "fields": {}, "version": 1}, ("version",), "extra_forbidden"),
    ],
)
def test_rules_reject_invalid_data(
    payload: dict, location: tuple[str, ...], error_type: str
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        Rules.model_validate(payload)

    (error,) = exc_info.value.errors()
    assert error["loc"] == location
    assert error["type"] == error_type
