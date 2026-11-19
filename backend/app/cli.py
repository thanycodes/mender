"""Mender from the terminal (run from backend/):

    uv run --env-file ../.env python -m app.cli generate ../testsite/books/index.html \\
        title author price:number in_stock:exists        # ask Llama for rules + preview
    uv run python -m app.cli seed-books                  # a job with hand-written rules
    uv run python -m app.cli run 1                       # apply job 1's rules, save rows
"""

import argparse
import json
import sys
from pathlib import Path

from app.fetch import FetchError
from app.llm import LLMError
from app.rules import FieldSpec, Rules

BOOKS = Path(__file__).resolve().parents[2] / "testsite" / "books"


def parse_field(arg: str) -> FieldSpec:
    """"price:number" → FieldSpec(name="price", type="number"). Type defaults to text."""
    name, _, type_ = arg.partition(":")
    return FieldSpec(name=name, type=type_ or "text")


def cmd_generate(args: argparse.Namespace) -> int:
    from app.tasks.generate_rules import generate_preview

    fields = [parse_field(f) for f in args.fields]
    preview = generate_preview(args.url, fields)
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


def cmd_seed_books(args: argparse.Namespace) -> int:
    """Phase 1: a job for our test bookshop, with hand-written rules already approved."""
    from app.db import SessionLocal
    from app.models import Job, RuleVersion

    rules = Rules.model_validate_json((BOOKS / "rules.v1.json").read_text())
    fields = [{"name": name, "type": rule.type} for name, rule in rules.fields.items()]
    with SessionLocal() as db:
        job = Job(
            url=str(BOOKS / "index.html"), field_schema=fields, status="active", schedule="manual"
        )
        job.versions.append(
            RuleVersion(
                version_no=1,
                rules=rules.model_dump(exclude_none=True),
                created_by="human",
                active=True,
            )
        )
        db.add(job)
        db.commit()
        print(f"created job {job.id}: {job.url}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from app.db import SessionLocal
    from app.tasks.run_job import run_job

    with SessionLocal() as db:
        run = run_job(db, args.job_id)
        print(json.dumps({"run_id": run.id, "health": run.health, "row_count": run.row_count}))
        if run.error:
            print(f"error: {run.error}", file=sys.stderr)
    return 0 if run.health == "ok" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mender")
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate", help="ask Llama for extraction rules + preview")
    generate.add_argument("url", help="http(s) URL or path to a local HTML file")
    generate.add_argument("fields", nargs="+", help="name or name:type (text, number, exists)")
    generate.add_argument("--save", type=Path, help="write the rules JSON to this file")
    generate.set_defaults(handler=cmd_generate)

    seed = commands.add_parser("seed-books", help="create a job for testsite/books")
    seed.set_defaults(handler=cmd_seed_books)

    run = commands.add_parser("run", help="run a job's active rules once and save the rows")
    run.add_argument("job_id", type=int)
    run.set_defaults(handler=cmd_run)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, FetchError, LLMError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
