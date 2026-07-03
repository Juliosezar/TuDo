"""Pydantic models for request/response bodies."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# Plain CRUD API (used by /api/todo, /api/idea)
# --------------------------------------------------------------------------


class TodoCreate(BaseModel):
    text: str
    due_date: Optional[str] = None
    due_time: Optional[str] = None


class IdeaCreate(BaseModel):
    text: str


class TodoOut(BaseModel):
    uuid: str
    text: str
    done: bool
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    done_at: Optional[str] = None
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: dict) -> "TodoOut":
        return cls(
            uuid=record["uuid"],
            text=record["text"],
            done=bool(record["done"]),
            due_date=record.get("due_date"),
            due_time=record.get("due_time"),
            done_at=record.get("done_at"),
            created_at=record["created_at"],
            updated_at=record["updated_at"],
        )


class IdeaOut(BaseModel):
    uuid: str
    text: str
    done: bool
    done_at: Optional[str] = None
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: dict) -> "IdeaOut":
        return cls(
            uuid=record["uuid"],
            text=record["text"],
            done=bool(record["done"]),
            done_at=record.get("done_at"),
            created_at=record["created_at"],
            updated_at=record["updated_at"],
        )


# --------------------------------------------------------------------------
# Sync protocol wire format
# --------------------------------------------------------------------------


class TodoSync(BaseModel):
    uuid: str
    text: str
    done: bool = False
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    done_at: Optional[str] = None
    deleted: bool = False
    deleted_at: Optional[str] = None
    created_at: str
    updated_at: str
    device_id: str

    @classmethod
    def from_record(cls, record: dict) -> "TodoSync":
        return cls(
            uuid=record["uuid"],
            text=record["text"],
            done=bool(record["done"]),
            due_date=record.get("due_date"),
            due_time=record.get("due_time"),
            done_at=record.get("done_at"),
            deleted=bool(record["deleted"]),
            deleted_at=record.get("deleted_at"),
            created_at=record["created_at"],
            updated_at=record["updated_at"],
            device_id=record["device_id"],
        )

    def to_record(self) -> dict:
        d = self.model_dump()
        d["done"] = 1 if d["done"] else 0
        d["deleted"] = 1 if d["deleted"] else 0
        return d


class IdeaSync(BaseModel):
    uuid: str
    text: str
    done: bool = False
    done_at: Optional[str] = None
    deleted: bool = False
    deleted_at: Optional[str] = None
    created_at: str
    updated_at: str
    device_id: str

    @classmethod
    def from_record(cls, record: dict) -> "IdeaSync":
        return cls(
            uuid=record["uuid"],
            text=record["text"],
            done=bool(record["done"]),
            done_at=record.get("done_at"),
            deleted=bool(record["deleted"]),
            deleted_at=record.get("deleted_at"),
            created_at=record["created_at"],
            updated_at=record["updated_at"],
            device_id=record["device_id"],
        )

    def to_record(self) -> dict:
        d = self.model_dump()
        d["done"] = 1 if d["done"] else 0
        d["deleted"] = 1 if d["deleted"] else 0
        return d


class SyncRequest(BaseModel):
    device_id: str
    last_synced_seq: int = 0
    todos: list[TodoSync] = Field(default_factory=list)
    ideas: list[IdeaSync] = Field(default_factory=list)


class SyncResponse(BaseModel):
    seq: int
    todos: list[TodoSync]
    ideas: list[IdeaSync]
