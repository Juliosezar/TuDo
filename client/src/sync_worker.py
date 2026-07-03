"""Performs a single push+pull sync round-trip with the server.

This is meant to run as a short-lived, detached background process (spawned
by cli.py, or by the periodic systemd/cron job installed by
connect_to_server.sh) so it never blocks a terminal command:

    python sync_worker.py sync

If the request fails for any reason (server down, network issue, etc.) this
gives up immediately - no retries, no backoff. Whatever didn't get synced
stays marked "dirty" locally and will simply be picked up next time a sync
is triggered (next mutation, next debounced read, or the next 5-minute
timer tick).
"""

from __future__ import annotations

import sys

try:
    import fcntl
except ImportError:  # pragma: no cover - Linux-only app
    fcntl = None

import db
import requests
import sync_config
from device import get_device_id

REQUEST_TIMEOUT_SECONDS = 10


def _acquire_lock():
    lock_file = open(sync_config.lock_path(), "w")
    if fcntl is None:
        return lock_file
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_file.close()
        return None
    return lock_file


def run_sync() -> bool:
    """Attempt one sync round-trip. Returns True on success, False otherwise.

    Safe to call even if syncing isn't enabled (it just no-ops), and safe to
    call concurrently from multiple processes (only one actually runs at a
    time; the rest no-op immediately rather than queueing up).
    """
    config = sync_config.load_config()
    if not config.get("enabled") or not config.get("server_url"):
        return False

    lock_file = _acquire_lock()
    if lock_file is None:
        return False  # another sync is already running; skip this one

    try:
        return _do_sync(config)
    finally:
        if fcntl is not None:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


def _to_wire(record: dict) -> dict:
    return {**record, "done": bool(record["done"]), "deleted": bool(record["deleted"])}


def _from_wire(record: dict) -> dict:
    return {
        **record,
        "done": 1 if record["done"] else 0,
        "deleted": 1 if record["deleted"] else 0,
    }


def _do_sync(config: dict) -> bool:
    db.init_db()
    sync_config.update_config(last_sync_attempt_at=db.now_sync_iso())

    dirty_todos = db.get_dirty_todos()
    dirty_ideas = db.get_dirty_ideas()

    payload = {
        "device_id": get_device_id(),
        "last_synced_seq": config.get("last_synced_seq", 0),
        "todos": [_to_wire(t) for t in dirty_todos],
        "ideas": [_to_wire(i) for i in dirty_ideas],
    }

    headers = {}
    if config.get("api_key"):
        headers["Authorization"] = f"Bearer {config['api_key']}"

    url = sync_config.sync_endpoint(config["server_url"])

    try:
        response = requests.post(
            url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        sync_config.update_config(last_sync_error=str(e))
        return False

    for record in data.get("todos", []):
        db.apply_remote_todo(_from_wire(record))
    for record in data.get("ideas", []):
        db.apply_remote_idea(_from_wire(record))

    # Only clear "dirty" for records that weren't changed again locally
    # while this sync was in flight (clear_dirty checks updated_at still
    # matches what we actually pushed).
    for t in dirty_todos:
        db.clear_dirty("todos", t["uuid"], t["updated_at"])
    for i in dirty_ideas:
        db.clear_dirty("ideas", i["uuid"], i["updated_at"])

    sync_config.update_config(
        last_synced_seq=data.get("seq", config.get("last_synced_seq", 0)),
        last_sync_success_at=db.now_sync_iso(),
        last_sync_error=None,
    )
    return True


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "sync":
        run_sync()
    else:
        print("Usage: sync_worker.py sync", file=sys.stderr)
        sys.exit(1)
