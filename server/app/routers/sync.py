"""The sync protocol: POST /api/sync/

A client sends its pending local changes (tagged with device_id + a Jalali
storage/HLC-ish `updated_at` timestamp used for last-write-wins) along with
the sequence number it last synced up to. The server merges the incoming
changes into its own store (last-write-wins per record), then replies with:

  - every change with seq > last_synced_seq (catch-up for this client), plus
  - the *current* winning version of every uuid the client just pushed (even
    if its own seq happens to be <= last_synced_seq already) - this matters
    when the client's push was rejected by LWW (e.g. due to clock skew), so
    the client is guaranteed to converge to the server's resolved state
    instead of silently drifting.
  - the new high-water-mark `seq` the client should remember for next time.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import db
from ..auth import require_api_key
from ..schemas import IdeaSync, SyncRequest, SyncResponse, TodoSync

router = APIRouter(
    prefix="/api/sync", tags=["sync"], dependencies=[Depends(require_api_key)]
)


@router.post("/", response_model=SyncResponse)
def sync(payload: SyncRequest):
    touched_todo_uuids: set[str] = set()
    touched_idea_uuids: set[str] = set()

    for todo in payload.todos:
        db.merge_todo(todo.to_record())
        touched_todo_uuids.add(todo.uuid)

    for idea in payload.ideas:
        db.merge_idea(idea.to_record())
        touched_idea_uuids.add(idea.uuid)

    todo_changes = {
        r["uuid"]: r for r in db.changes_since("todos", payload.last_synced_seq)
    }
    idea_changes = {
        r["uuid"]: r for r in db.changes_since("ideas", payload.last_synced_seq)
    }

    # Force-include the resolved version of every uuid the client just
    # pushed, even if it wasn't picked up by the seq-based query above.
    for item_uuid in touched_todo_uuids:
        if item_uuid not in todo_changes:
            record = db.get_by_uuid("todos", item_uuid)
            if record is not None:
                todo_changes[item_uuid] = record

    for item_uuid in touched_idea_uuids:
        if item_uuid not in idea_changes:
            record = db.get_by_uuid("ideas", item_uuid)
            if record is not None:
                idea_changes[item_uuid] = record

    return SyncResponse(
        seq=db.current_seq(),
        todos=[TodoSync.from_record(r) for r in todo_changes.values()],
        ideas=[IdeaSync.from_record(r) for r in idea_changes.values()],
    )
