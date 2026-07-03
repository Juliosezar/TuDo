"""Plain CRUD API for todos: /api/todo/...

This is independent of the sync protocol - it's meant for direct use (e.g.
scripts, an AI agent, curl) and mirrors what the terminal client can do:
add, remove, done, undone, list, history.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import db
from ..auth import require_api_key
from ..schemas import TodoCreate, TodoOut

router = APIRouter(
    prefix="/api/todo", tags=["todo"], dependencies=[Depends(require_api_key)]
)


@router.post("/", response_model=TodoOut)
def add_todo(payload: TodoCreate):
    record = db.create_todo(payload.text, payload.due_date, payload.due_time)
    return TodoOut.from_record(record)


@router.get("/", response_model=list[TodoOut])
def list_todos(include_done: bool = True):
    return [TodoOut.from_record(r) for r in db.list_todos(include_done=include_done)]


@router.get("/history", response_model=list[TodoOut])
def todo_history(days: int = 7):
    return [TodoOut.from_record(r) for r in db.list_todos_history(days=days)]


@router.get("/{item_uuid}", response_model=TodoOut)
def get_todo(item_uuid: str):
    record = db.get_by_uuid("todos", item_uuid)
    if record is None or record["deleted"]:
        raise HTTPException(status_code=404, detail="Todo not found.")
    return TodoOut.from_record(record)


@router.post("/{item_uuid}/done", response_model=TodoOut)
def mark_done(item_uuid: str):
    record = db.set_todo_done(item_uuid, True)
    if record is None:
        raise HTTPException(status_code=404, detail="Todo not found.")
    return TodoOut.from_record(record)


@router.post("/{item_uuid}/undone", response_model=TodoOut)
def mark_undone(item_uuid: str):
    record = db.set_todo_done(item_uuid, False)
    if record is None:
        raise HTTPException(status_code=404, detail="Todo not found.")
    return TodoOut.from_record(record)


@router.delete("/{item_uuid}")
def remove_todo(item_uuid: str):
    if not db.delete_todo(item_uuid):
        raise HTTPException(status_code=404, detail="Todo not found.")
    return {"ok": True}
