"""tudo sync server entry point.

Run with: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI

from . import db
from .routers import ideas, sync, todos

app = FastAPI(title="tudo server", version="1.0.0")


@app.on_event("startup")
def on_startup() -> None:
    db.init_db()


@app.get("/api/health")
def health():
    """Unauthenticated connectivity check, used by connect_to_server.sh."""
    return {"status": "ok"}


app.include_router(todos.router)
app.include_router(ideas.router)
app.include_router(sync.router)
