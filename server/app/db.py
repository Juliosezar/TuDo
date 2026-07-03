"""SQLite persistence for the tudo sync server.

Every record (todo/idea) is keyed by a client-generated UUID and carries an
``updated_at`` timestamp + ``device_id``, used to resolve conflicts with a
simple last-write-wins (LWW) rule: the record with the later ``updated_at``
wins; ties are broken by comparing ``device_id`` so the outcome is
deterministic on every replica.

Every record also gets a server-assigned, monotonically increasing ``seq``
whenever it is created or its LWW-winning version changes. Clients pull
"everything with seq > last_synced_seq" to catch up after being offline.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid as uuid_lib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional

from . import config

_WRITE_LOCK = threading.Lock()

SERVER_DEVICE_ID = "server-api"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _WRITE_LOCK, get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS counters (
                name TEXT PRIMARY KEY,
                value INTEGER NOT NULL
            )
            """
        )
        conn.execute("INSERT OR IGNORE INTO counters (name, value) VALUES ('seq', 0)")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                uuid TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                due_date TEXT,
                due_time TEXT,
                done_at TEXT,
                deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                device_id TEXT NOT NULL,
                seq INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ideas (
                uuid TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                done_at TEXT,
                deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                device_id TEXT NOT NULL,
                seq INTEGER NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_todos_seq ON todos(seq)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ideas_seq ON ideas(seq)")


def _next_seq(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "UPDATE counters SET value = value + 1 WHERE name = 'seq' RETURNING value"
    ).fetchone()
    return row[0]


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


TODO_COLUMNS = [
    "uuid",
    "text",
    "done",
    "due_date",
    "due_time",
    "done_at",
    "deleted",
    "deleted_at",
    "created_at",
    "updated_at",
    "device_id",
]
IDEA_COLUMNS = [
    "uuid",
    "text",
    "done",
    "done_at",
    "deleted",
    "deleted_at",
    "created_at",
    "updated_at",
    "device_id",
]


def _is_newer(incoming: dict, existing: sqlite3.Row) -> bool:
    if incoming["updated_at"] != existing["updated_at"]:
        return incoming["updated_at"] > existing["updated_at"]
    return incoming["device_id"] > existing["device_id"]


def _upsert(
    conn: sqlite3.Connection, table: str, columns: list[str], incoming: dict
) -> dict:
    """Merge an incoming record into `table` using last-write-wins.

    Returns the final (winning) row as a dict, whether or not the incoming
    record was actually applied.
    """
    existing = conn.execute(
        f"SELECT * FROM {table} WHERE uuid = ?", (incoming["uuid"],)
    ).fetchone()

    if existing is None:
        seq = _next_seq(conn)
        values = [incoming.get(col) for col in columns]
        placeholders = ", ".join("?" for _ in columns)
        conn.execute(
            f"INSERT INTO {table} ({', '.join(columns)}, seq) VALUES ({placeholders}, ?)",
            (*values, seq),
        )
        return {**incoming, "seq": seq}

    if not _is_newer(incoming, existing):
        return _row_to_dict(existing)

    seq = _next_seq(conn)
    assignments = ", ".join(f"{col} = ?" for col in columns if col != "uuid")
    values = [incoming.get(col) for col in columns if col != "uuid"]
    conn.execute(
        f"UPDATE {table} SET {assignments}, seq = ? WHERE uuid = ?",
        (*values, seq, incoming["uuid"]),
    )
    return {**incoming, "seq": seq}


def merge_todo(record: dict) -> dict:
    with _WRITE_LOCK, get_connection() as conn:
        return _upsert(conn, "todos", TODO_COLUMNS, record)


def merge_idea(record: dict) -> dict:
    with _WRITE_LOCK, get_connection() as conn:
        return _upsert(conn, "ideas", IDEA_COLUMNS, record)


def current_seq() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM counters WHERE name = 'seq'").fetchone()
        return row["value"] if row else 0


def changes_since(table: str, since_seq: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE seq > ? ORDER BY seq ASC", (since_seq,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_by_uuid(table: str, item_uuid: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT * FROM {table} WHERE uuid = ?", (item_uuid,)
        ).fetchone()
    return _row_to_dict(row) if row else None


# --------------------------------------------------------------------------
# Plain CRUD helpers backing /api/todo and /api/idea (for direct API use,
# e.g. from a script or an AI agent, independent of the sync protocol).
# --------------------------------------------------------------------------


def create_todo(
    text: str, due_date: Optional[str] = None, due_time: Optional[str] = None
) -> dict:
    now = now_iso()
    record = {
        "uuid": str(uuid_lib.uuid4()),
        "text": text,
        "done": 0,
        "due_date": due_date,
        "due_time": due_time,
        "done_at": None,
        "deleted": 0,
        "deleted_at": None,
        "created_at": now,
        "updated_at": now,
        "device_id": SERVER_DEVICE_ID,
    }
    with _WRITE_LOCK, get_connection() as conn:
        seq = _next_seq(conn)
        conn.execute(
            "INSERT INTO todos (uuid, text, done, due_date, due_time, done_at, deleted, deleted_at, "
            "created_at, updated_at, device_id, seq) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record["uuid"],
                record["text"],
                record["done"],
                record["due_date"],
                record["due_time"],
                record["done_at"],
                record["deleted"],
                record["deleted_at"],
                record["created_at"],
                record["updated_at"],
                record["device_id"],
                seq,
            ),
        )
    return {**record, "seq": seq}


def set_todo_done(item_uuid: str, done: bool) -> Optional[dict]:
    existing = get_by_uuid("todos", item_uuid)
    if existing is None or existing["deleted"]:
        return None
    now = now_iso()
    record = {
        **existing,
        "done": 1 if done else 0,
        "done_at": now if done else None,
        "updated_at": now,
        "device_id": SERVER_DEVICE_ID,
    }
    return merge_todo(record)


def delete_todo(item_uuid: str) -> bool:
    existing = get_by_uuid("todos", item_uuid)
    if existing is None or existing["deleted"]:
        return False
    now = now_iso()
    record = {
        **existing,
        "deleted": 1,
        "deleted_at": now,
        "updated_at": now,
        "device_id": SERVER_DEVICE_ID,
    }
    merge_todo(record)
    return True


def list_todos(include_done: bool = True) -> list[dict]:
    query = "SELECT * FROM todos WHERE deleted = 0"
    if not include_done:
        query += " AND done = 0"
    query += " ORDER BY seq ASC"
    with get_connection() as conn:
        rows = conn.execute(query).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_todos_history(days: int = config.DEFAULT_HISTORY_DAYS) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(
        timespec="microseconds"
    )
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM todos WHERE done = 1 AND deleted = 0 AND done_at >= ? ORDER BY done_at DESC",
            (cutoff,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def create_idea(text: str) -> dict:
    now = now_iso()
    record = {
        "uuid": str(uuid_lib.uuid4()),
        "text": text,
        "done": 0,
        "done_at": None,
        "deleted": 0,
        "deleted_at": None,
        "created_at": now,
        "updated_at": now,
        "device_id": SERVER_DEVICE_ID,
    }
    with _WRITE_LOCK, get_connection() as conn:
        seq = _next_seq(conn)
        conn.execute(
            "INSERT INTO ideas (uuid, text, done, done_at, deleted, deleted_at, created_at, updated_at, "
            "device_id, seq) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record["uuid"],
                record["text"],
                record["done"],
                record["done_at"],
                record["deleted"],
                record["deleted_at"],
                record["created_at"],
                record["updated_at"],
                record["device_id"],
                seq,
            ),
        )
    return {**record, "seq": seq}


def set_idea_done(item_uuid: str, done: bool) -> Optional[dict]:
    existing = get_by_uuid("ideas", item_uuid)
    if existing is None or existing["deleted"]:
        return None
    now = now_iso()
    record = {
        **existing,
        "done": 1 if done else 0,
        "done_at": now if done else None,
        "updated_at": now,
        "device_id": SERVER_DEVICE_ID,
    }
    return merge_idea(record)


def delete_idea(item_uuid: str) -> bool:
    existing = get_by_uuid("ideas", item_uuid)
    if existing is None or existing["deleted"]:
        return False
    now = now_iso()
    record = {
        **existing,
        "deleted": 1,
        "deleted_at": now,
        "updated_at": now,
        "device_id": SERVER_DEVICE_ID,
    }
    merge_idea(record)
    return True


def list_ideas(include_done: bool = True) -> list[dict]:
    query = "SELECT * FROM ideas WHERE deleted = 0"
    if not include_done:
        query += " AND done = 0"
    query += " ORDER BY seq ASC"
    with get_connection() as conn:
        rows = conn.execute(query).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_ideas_history(days: int = config.DEFAULT_HISTORY_DAYS) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(
        timespec="microseconds"
    )
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM ideas WHERE done = 1 AND deleted = 0 AND done_at >= ? ORDER BY done_at DESC",
            (cutoff,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]
