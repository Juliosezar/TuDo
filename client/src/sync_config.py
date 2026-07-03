"""Reads/writes the client's sync configuration.

Stored at ~/.config/tudo/sync.json. Presence of this file with
"enabled": true is what turns on all syncing behavior in the client
(connect_to_server.sh creates it, disconnect_server.sh removes it).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - Linux-only app
    fcntl = None

DEBOUNCE_SECONDS = (
    60  # minimum time between opportunistic (read-triggered) sync attempts
)


def config_dir() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home) if config_home else Path.home() / ".config"
    d = base / "tudo"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return config_dir() / "sync.json"


def lock_path() -> Path:
    return config_dir() / "sync.lock"


_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "server_url": None,
    "api_key": None,
    "last_synced_seq": 0,
    "last_sync_attempt_at": None,
    "last_sync_success_at": None,
    "last_sync_error": None,
}


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        return dict(_DEFAULTS)
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULTS)
    return {**_DEFAULTS, **data}


def save_config(config: dict) -> None:
    path = config_path()
    tmp_path = path.with_suffix(".json.tmp")
    with open(tmp_path, "w") as f:
        if fcntl:
            fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(config, f, indent=2)
    os.replace(tmp_path, path)


def update_config(**changes: Any) -> dict:
    config = load_config()
    config.update(changes)
    save_config(config)
    return config


def is_enabled() -> bool:
    return bool(load_config().get("enabled") and load_config().get("server_url"))


def disable() -> None:
    path = config_path()
    if path.exists():
        path.unlink()


def sync_endpoint(base_url: str) -> str:
    return base_url.rstrip("/") + "/sync/"


def todo_endpoint(base_url: str) -> str:
    return base_url.rstrip("/") + "/todo/"


def idea_endpoint(base_url: str) -> str:
    return base_url.rstrip("/") + "/idea/"
