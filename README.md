# Mender

Self-healing web scrapers. You describe the data you want from a page, an LLM writes CSS-selector extraction rules **once**, and cheap deterministic code runs them on a schedule. The model is called again only when validation detects that the rules broke.

> Status: **Phase 1, in progress.** Plain scraper with hand-written rules, Postgres, FastAPI and Next.js. No AI yet.

The full design is in [`docs/MENDER_PROJECT_PLAN.md`](docs/MENDER_PROJECT_PLAN.md).

## Stack
Next.js · TypeScript · Tailwind | FastAPI · Pydantic · SQLAlchemy · Alembic | Postgres 17 | Redis + RQ (Phase 3) | httpx · Playwright · selectolax | Llama 4 (Phase 2)

## Roadmap
- [ ] Phase 1: plain scraper with a web page
- [ ] Phase 2: AI writes the rules
- [ ] Phase 3: scheduling and background workers
- [ ] Phase 4: validation and self-healing
- [ ] Phase 5: evals, auth, deploy

## Running locally

Database (Postgres in Docker; [OrbStack](https://orbstack.dev) or Docker Desktop):

```bash
cp .env.example .env                     # once; .env is gitignored
docker compose up -d --wait              # Postgres on localhost:5432 (+ a mender_test DB for pytest)
cd backend && uv run alembic upgrade head   # create/upgrade the tables
```

Backend (Python 3.12, [uv](https://docs.astral.sh/uv/)):

```bash
cd backend
uv sync                                  # create .venv and install deps
uv run uvicorn app.main:app --reload     # API on http://localhost:8000 (docs at /docs)
uv run ruff check . && uv run pytest     # lint + tests (DB tests need Postgres running)
```
