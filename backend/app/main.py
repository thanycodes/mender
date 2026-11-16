"""The API server: Mender's one controlled entry point.

Rule: the API only does fast work (read the DB, write a row, queue a task).
Anything slow (fetching pages, calling Llama) belongs in a worker.
"""

from fastapi import FastAPI

app = FastAPI(title="Mender API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check. Used by humans, CI, and later by Docker/hosting health probes."""
    return {"status": "ok"}
