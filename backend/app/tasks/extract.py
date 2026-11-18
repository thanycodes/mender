"""Apply extraction rules on every scheduled run, so this hot path stays fast and deterministic."""

from math import isfinite
from unicodedata import category

from selectolax.lexbor import LexborHTMLParser

from app.rules import Rules


def _parse_number(value: str) -> float | None:
    if value and category(value[0]) == "Sc":
        value = value[1:]
    if value and category(value[-1]) == "Sc":
        value = value[:-1]
    try:
        number = float(value.replace(",", ""))
    except ValueError:
        return None
    return number if isfinite(number) else None


def extract(html: str, rules: Rules) -> list[dict]:
    """Leave zero rows and missing values visible for downstream validation."""
    document = LexborHTMLParser(html)
    records = []
    for row in document.css(rules.row_selector):
        record = {}
        for name, field in rules.fields.items():
            element = row.css_first(field.selector)
            # Selectolax includes the row itself, but fields are matched inside it.
            if element == row:
                element = next((match for match in row.css(field.selector) if match != row), None)
            if field.type == "exists":
                record[name] = element is not None
            elif element is None:
                record[name] = None
            else:
                value = " ".join(element.text().split())
                if field.type == "number":
                    record[name] = _parse_number(value)
                else:
                    record[name] = value.removeprefix(field.strip_prefix or "").lstrip()
        records.append(record)
    return records
