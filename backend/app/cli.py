"""Try rule generation from the terminal until the web form exists.

    uv run --env-file ../.env python -m app.cli ../testsite/books/index.html \\
        title author price:number in_stock:exists --save /tmp/rules.json
"""

import argparse
import sys
from pathlib import Path

from app.fetch import FetchError
from app.llm import LLMError
from app.rules import FieldSpec
from app.tasks.generate_rules import generate_preview


def parse_field(arg: str) -> FieldSpec:
    """"price:number" → FieldSpec(name="price", type="number"). Type defaults to text."""
    name, _, type_ = arg.partition(":")
    return FieldSpec(name=name, type=type_ or "text")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask Llama for extraction rules and preview them")
    parser.add_argument("url", help="http(s) URL or path to a local HTML file")
    parser.add_argument("fields", nargs="+", help="name or name:type (text, number, exists)")
    parser.add_argument("--save", type=Path, help="write the rules JSON to this file")
    args = parser.parse_args(argv)

    try:
        fields = [parse_field(f) for f in args.fields]
        preview = generate_preview(args.url, fields)
    except (ValueError, FetchError, LLMError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    rules_json = preview.rules.model_dump_json(indent=2, exclude_none=True)
    print(rules_json)
    print(f"\n{preview.row_count} rows; attempts={preview.attempts}; tokens={preview.tokens_used}")
    for row in preview.rows:
        print(" ", row)
    for warning in preview.warnings:
        print(f"warning: {warning}")
    if args.save:
        args.save.write_text(rules_json + "\n", encoding="utf-8")
        print(f"saved {args.save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
