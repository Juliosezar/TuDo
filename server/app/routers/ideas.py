"""Plain CRUD API for ideas: /api/idea/...

Independent of the sync protocol - meant for direct use (scripts, an AI
agent, curl). Mirrors the terminal client: add, remove, done, undone, list,
history.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import db
from ..auth import require_api_key
from ..schemas import IdeaCreate, IdeaOut

router = APIRouter(
    prefix="/api/idea", tags=["idea"], dependencies=[Depends(require_api_key)]
)


@router.post("/", response_model=IdeaOut)
def add_idea(payload: IdeaCreate):
    record = db.create_idea(payload.text)
    return IdeaOut.from_record(record)


@router.get("/", response_model=list[IdeaOut])
def list_ideas(include_done: bool = True):
    return [IdeaOut.from_record(r) for r in db.list_ideas(include_done=include_done)]


@router.get("/history", response_model=list[IdeaOut])
def idea_history(days: int = 7):
    return [IdeaOut.from_record(r) for r in db.list_ideas_history(days=days)]


@router.get("/{item_uuid}", response_model=IdeaOut)
def get_idea(item_uuid: str):
    record = db.get_by_uuid("ideas", item_uuid)
    if record is None or record["deleted"]:
        raise HTTPException(status_code=404, detail="Idea not found.")
    return IdeaOut.from_record(record)


@router.post("/{item_uuid}/done", response_model=IdeaOut)
def mark_done(item_uuid: str):
    record = db.set_idea_done(item_uuid, True)
    if record is None:
        raise HTTPException(status_code=404, detail="Idea not found.")
    return IdeaOut.from_record(record)


@router.post("/{item_uuid}/undone", response_model=IdeaOut)
def mark_undone(item_uuid: str):
    record = db.set_idea_done(item_uuid, False)
    if record is None:
        raise HTTPException(status_code=404, detail="Idea not found.")
    return IdeaOut.from_record(record)


@router.delete("/{item_uuid}")
def remove_idea(item_uuid: str):
    if not db.delete_idea(item_uuid):
        raise HTTPException(status_code=404, detail="Idea not found.")
    return {"ok": True}
