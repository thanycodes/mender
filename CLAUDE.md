# Mender: notes for Claude

Self-healing web scraper, built as a learning and resume project. Full design: `docs/MENDER_PROJECT_PLAN.md`. Read it before any architectural change.

## How we work
- The owner is learning full-stack development and architecture. **Explain the *why*** behind each step, briefly.
- Build in **small slices**. Each slice ends with: verification commands the owner runs, then **one Conventional Commit pushed to `main`** on `github.com/thanycodes/mender`. Tag the end of each phase (`phase-1`, …).
- Don't jump ahead of the current phase (e.g. no AI before Phase 2, no Redis before Phase 3).

## Core rules of the design
- The API never does slow work, and normal runs never call the AI.
- Postgres is the source of truth. Redis holds only temporary tasks.
- Extraction rules are **JSON data, not code**. Every version is kept.
- `backend/app/llm.py` is the ONLY module that calls Llama.
- Save a Run and its Records in one transaction. `UNIQUE(job_id, scheduled_for)` keeps retries idempotent.

## Layout and tooling
- `backend/`: Python 3.12, managed with **uv** (`uv sync`, `uv run …`). FastAPI app in `app/`, worker code in `app/tasks/`, Alembic migrations in `alembic/`.
- `web/`: Next.js (App Router, TypeScript, Tailwind), npm.
- `testsite/`: our own static pages to scrape and deliberately "redesign" for heal evals.
- `docker-compose.yml`: infra only (Postgres now, Redis in Phase 3). The API and web run natively in dev.
- Quality: `uv run ruff check .`, `uv run pytest`. CI is in `.github/workflows/`.
