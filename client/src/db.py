"""SQLite persistence layer for todos and ideas.

Due dates/times are stored exactly as provided by the caller (the CLI layer
is responsible for turning Jalali calendar input into the storage strings
via ``persian_date``). This module only deals with plain strings and does
not know anything about calendars.

"Done" items stay visible for 24 hours after being marked done, then they
are only reachable through the ``*_history`` functions.

Every record also carries fields used for multi-device syncing (see
``sync_worker.py``):

- ``uuid``: a globally unique, client-generated identity. The local ``id``
  column is only ever used for CLI convenience (e.g. ``todo done 3``) and is
  never shared between devices - the same todo can have different local
  ``id``s on different devices, but the same ``uuid`` everywhere.
- ``updated_at``: a UTC timestamp (microsecond precision) used to resolve
  conflicts between devices with a last-write-wins rule.
- ``device_id``: which device last wrote this record.
- ``deleted``/``deleted_at``: soft-delete tombstone, so deletions can
  propagate to other devices instead of just disappearing silently.
- ``dirty``: set whenever a record is created/changed locally and cleared
  once a sync has confirmedly pushed it - i.e. the local "outbox".
"""

from __future__ import annotations

import os
import sqlite3
import uuid as uuid_lib
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

from device import get_device_id

DONE_VISIBLE_HOURS = 24
DEFAULT_HISTORY_DAYS = 7
TOMBSTONE_RETENTION_DAYS = 30


def get_db_path() -> Path:
    """Return the path to the sqlite database, creating its directory if needed."""
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    db_dir = base / "tudo"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "tudo.db"


def now_local_iso() -> str:
    """Local timestamp (naive, seconds precision) - for display fields only."""
    return datetime.now().isoformat(timespec="seconds")


def now_sync_iso() -> str:
    """UTC timestamp (microsecond precision) - used for LWW conflict resolution.

    Using UTC (rather than local time) keeps comparisons correct even if a
    user's devices are in different timezones.
    """
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_column(
    conn: sqlite3.Connection, table: str, column: str, coltype: str
) -> None:
    existing = {
        row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def _backfill_sync_columns(conn: sqlite3.Connection, table: str) -> None:
    """Give any pre-sync rows a uuid/updated_at/device_id so they can sync too."""
    device_id = get_device_id()
    rows = conn.execute(
        f"SELECT id, created_at FROM {table} WHERE uuid IS NULL"
    ).fetchall()
    for row in rows:
        conn.execute(
            f"UPDATE {table} SET uuid = ?, updated_at = ?, device_id = ?, dirty = 1, deleted = 0 WHERE id = ?",
            (
                str(uuid_lib.uuid4()),
                row["created_at"] or now_sync_iso(),
                device_id,
                row["id"],
            ),
        )


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                due_date TEXT,
                due_time TEXT,
                done_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                done_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        # Migrate databases created by older versions of tudo.
        _ensure_column(conn, "todos", "due_time", "TEXT")
        _ensure_column(conn, "todos", "done_at", "TEXT")
        _ensure_column(conn, "ideas", "done", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "ideas", "done_at", "TEXT")

        for table in ("todos", "ideas"):
            _ensure_column(conn, table, "uuid", "TEXT")
            _ensure_column(conn, table, "updated_at", "TEXT")
            _ensure_column(conn, table, "device_id", "TEXT")
            _ensure_column(conn, table, "deleted", "INTEGER NOT NULL DEFAULT 0")
            _ensure_column(conn, table, "deleted_at", "TEXT")
            _ensure_column(conn, table, "dirty", "INTEGER NOT NULL DEFAULT 1")
            _backfill_sync_columns(conn, table)
            conn.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_uuid ON {table}(uuid)"
            )

        _purge_old_tombstones(conn)


def _purge_old_tombstones(conn: sqlite3.Connection) -> None:
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=TOMBSTONE_RETENTION_DAYS)
    ).isoformat(timespec="microseconds")
    for table in ("todos", "ideas"):
        conn.execute(
            f"DELETE FROM {table} WHERE deleted = 1 AND dirty = 0 AND deleted_at IS NOT NULL AND deleted_at < ?",
            (cutoff,),
        )


@dataclass
class Todo:
    id: int
    uuid: str
    text: str
    done: bool
    due_date: Optional[str]
    due_time: Optional[str]
    done_at: Optional[str]
    created_at: str


@dataclass
class Idea:
    id: int
    uuid: str
    text: str
    done: bool
    done_at: Optional[str]
    created_at: str


def _row_to_todo(row: sqlite3.Row) -> Todo:
    return Todo(
        id=row["id"],
        uuid=row["uuid"],
        text=row["text"],
        done=bool(row["done"]),
        due_date=row["due_date"],
        due_time=row["due_time"],
        done_at=row["done_at"],
        created_at=row["created_at"],
    )


def _row_to_idea(row: sqlite3.Row) -> Idea:
    return Idea(
        id=row["id"],
        uuid=row["uuid"],
        text=row["text"],
        done=bool(row["done"]),
        done_at=row["done_at"],
        created_at=row["created_at"],
    )


# --------------------------------------------------------------------------
# Todos
# --------------------------------------------------------------------------


def add_todo(
    text: str, due_date: Optional[str] = None, due_time: Optional[str] = None
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO todos (text, done, due_date, due_time, done_at, created_at, "
            "uuid, updated_at, device_id, deleted, deleted_at, dirty) "
            "VALUES (?, 0, ?, ?, NULL, ?, ?, ?, ?, 0, NULL, 1)",
            (
                text,
                due_date,
                due_time,
                now_local_iso(),
                str(uuid_lib.uuid4()),
                now_sync_iso(),
                get_device_id(),
            ),
        )
        assert cur.lastrowid is not None
        return cur.lastrowid


def list_todos() -> list[Todo]:
    """Active todos: not-done ones, plus done ones for 24h after completion."""
    cutoff = (datetime.now() - timedelta(hours=DONE_VISIBLE_HOURS)).isoformat(
        timespec="seconds"
    )
    query = (
        "SELECT id, uuid, text, done, due_date, due_time, done_at, created_at FROM todos "
        "WHERE deleted = 0 AND (done = 0 OR (done = 1 AND done_at >= ?)) "
        "ORDER BY id ASC"
    )
    with get_connection() as conn:
        rows = conn.execute(query, (cutoff,)).fetchall()
    return [_row_to_todo(r) for r in rows]


def list_todos_history(days: int = DEFAULT_HISTORY_DAYS) -> list[Todo]:
    """Todos marked done within the last ``days`` days, most recent first."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    query = (
        "SELECT id, uuid, text, done, due_date, due_time, done_at, created_at FROM todos "
        "WHERE deleted = 0 AND done = 1 AND done_at >= ? "
        "ORDER BY done_at DESC"
    )
    with get_connection() as conn:
        rows = conn.execute(query, (cutoff,)).fetchall()
    return [_row_to_todo(r) for r in rows]


def get_todo(todo_id: int) -> Optional[Todo]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, uuid, text, done, due_date, due_time, done_at, created_at "
            "FROM todos WHERE id = ? AND deleted = 0",
            (todo_id,),
        ).fetchone()
    return _row_to_todo(row) if row else None


def set_todo_done(todo_id: int, done: bool = True) -> bool:
    done_at = now_local_iso() if done else None
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE todos SET done = ?, done_at = ?, updated_at = ?, device_id = ?, dirty = 1 "
            "WHERE id = ? AND deleted = 0",
            (1 if done else 0, done_at, now_sync_iso(), get_device_id(), todo_id),
        )
        return cur.rowcount > 0


def remove_todo(todo_id: int) -> bool:
    """Soft-delete: keeps a tombstone around so the deletion can sync."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE todos SET deleted = 1, deleted_at = ?, updated_at = ?, device_id = ?, dirty = 1 "
            "WHERE id = ? AND deleted = 0",
            (now_sync_iso(), now_sync_iso(), get_device_id(), todo_id),
        )
        return cur.rowcount > 0


# --------------------------------------------------------------------------
# Ideas
# --------------------------------------------------------------------------


def add_idea(text: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO ideas (text, done, done_at, created_at, uuid, updated_at, device_id, "
            "deleted, deleted_at, dirty) VALUES (?, 0, NULL, ?, ?, ?, ?, 0, NULL, 1)",
            (
                text,
                now_local_iso(),
                str(uuid_lib.uuid4()),
                now_sync_iso(),
                get_device_id(),
            ),
        )
        assert cur.lastrowid is not None
        return cur.lastrowid


def list_ideas() -> list[Idea]:
    """Active ideas: not-done ones, plus done ones for 24h after completion."""
    cutoff = (datetime.now() - timedelta(hours=DONE_VISIBLE_HOURS)).isoformat(
        timespec="seconds"
    )
    query = (
        "SELECT id, uuid, text, done, done_at, created_at FROM ideas "
        "WHERE deleted = 0 AND (done = 0 OR (done = 1 AND done_at >= ?)) "
        "ORDER BY id ASC"
    )
    with get_connection() as conn:
        rows = conn.execute(query, (cutoff,)).fetchall()
    return [_row_to_idea(r) for r in rows]


def list_ideas_history(days: int = DEFAULT_HISTORY_DAYS) -> list[Idea]:
    """Ideas marked done within the last ``days`` days, most recent first."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    query = (
        "SELECT id, uuid, text, done, done_at, created_at FROM ideas "
        "WHERE deleted = 0 AND done = 1 AND done_at >= ? "
        "ORDER BY done_at DESC"
    )
    with get_connection() as conn:
        rows = conn.execute(query, (cutoff,)).fetchall()
    return [_row_to_idea(r) for r in rows]


def get_idea(idea_id: int) -> Optional[Idea]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, uuid, text, done, done_at, created_at FROM ideas WHERE id = ? AND deleted = 0",
            (idea_id,),
        ).fetchone()
    return _row_to_idea(row) if row else None


def set_idea_done(idea_id: int, done: bool = True) -> bool:
    done_at = now_local_iso() if done else None
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE ideas SET done = ?, done_at = ?, updated_at = ?, device_id = ?, dirty = 1 "
            "WHERE id = ? AND deleted = 0",
            (1 if done else 0, done_at, now_sync_iso(), get_device_id(), idea_id),
        )
        return cur.rowcount > 0


def remove_idea(idea_id: int) -> bool:
    """Soft-delete: keeps a tombstone around so the deletion can sync."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE ideas SET deleted = 1, deleted_at = ?, updated_at = ?, device_id = ?, dirty = 1 "
            "WHERE id = ? AND deleted = 0",
            (now_sync_iso(), now_sync_iso(), get_device_id(), idea_id),
        )
        return cur.rowcount > 0


# --------------------------------------------------------------------------
# Sync support: outbox (dirty rows) and applying remote changes (LWW merge)
# --------------------------------------------------------------------------

SYNC_COLUMNS = [
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
SYNC_COLUMNS_IDEA = [c for c in SYNC_COLUMNS if c not in ("due_date", "due_time")]


def get_dirty_todos() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT {', '.join(SYNC_COLUMNS)} FROM todos WHERE dirty = 1"
        ).fetchall()
    return [dict(r) for r in rows]


def get_dirty_ideas() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT {', '.join(SYNC_COLUMNS_IDEA)} FROM ideas WHERE dirty = 1"
        ).fetchall()
    return [dict(r) for r in rows]


def clear_dirty(table: str, item_uuid: str, updated_at: str) -> None:
    """Clear the dirty flag, but only if the record wasn't changed again
    (locally) since it was read for pushing."""
    with get_connection() as conn:
        conn.execute(
            f"UPDATE {table} SET dirty = 0 WHERE uuid = ? AND updated_at = ?",
            (item_uuid, updated_at),
        )


def _is_newer(incoming: dict, existing: sqlite3.Row) -> bool:
    if incoming["updated_at"] != existing["updated_at"]:
        return incoming["updated_at"] > existing["updated_at"]
    return incoming["device_id"] > existing["device_id"]


def _apply_remote(
    conn: sqlite3.Connection, table: str, columns: list[str], record: dict
) -> None:
    existing = conn.execute(
        f"SELECT * FROM {table} WHERE uuid = ?", (record["uuid"],)
    ).fetchone()

    if existing is None:
        placeholders = ", ".join("?" for _ in columns)
        conn.execute(
            f"INSERT INTO {table} ({', '.join(columns)}, dirty) VALUES ({placeholders}, 0)",
            tuple(record.get(c) for c in columns),
        )
        return

    if not _is_newer(record, existing):
        return  # local copy is already the winner; nothing to do

    assignments = ", ".join(f"{col} = ?" for col in columns if col != "uuid")
    values = [record.get(col) for col in columns if col != "uuid"]
    conn.execute(
        f"UPDATE {table} SET {assignments}, dirty = 0 WHERE uuid = ?",
        (*values, record["uuid"]),
    )


def apply_remote_todo(record: dict) -> None:
    with get_connection() as conn:
        _apply_remote(conn, "todos", SYNC_COLUMNS, record)


def apply_remote_idea(record: dict) -> None:
    with get_connection() as conn:
        _apply_remote(conn, "ideas", SYNC_COLUMNS_IDEA, record)
