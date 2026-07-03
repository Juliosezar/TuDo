"""Decides when to kick off a background sync, without ever blocking the
caller (the actual network I/O always happens in a separate, detached
process - see sync_worker.py)."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import sync_config

_WORKER_PATH = Path(__file__).parent / "sync_worker.py"


def _spawn() -> None:
    subprocess.Popen(
        [sys.executable, str(_WORKER_PATH), "sync"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def after_mutation() -> None:
    """Call after a local add/done/undone/remove: always fire a background
    sync attempt (if enabled) so changes propagate quickly, without making
    the command that just ran wait for it."""
    if sync_config.is_enabled():
        _spawn()


def before_read() -> None:
    """Call before rendering the dashboard/list: opportunistically fire a
    background sync (if enabled and it's been a while since the last
    attempt), then the caller should immediately render whatever local data
    it already has - never wait for this."""
    config = sync_config.load_config()
    if not config.get("enabled") or not config.get("server_url"):
        return

    last_attempt = config.get("last_sync_attempt_at")
    if last_attempt:
        try:
            elapsed = (
                datetime.now(timezone.utc) - datetime.fromisoformat(last_attempt)
            ).total_seconds()
            if elapsed < sync_config.DEBOUNCE_SECONDS:
                return
        except ValueError:
            pass

    _spawn()
