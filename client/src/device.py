"""A stable per-installation device identifier.

This exists independently of whether syncing is enabled: every record
created locally (todo/idea) is tagged with this id so that, whenever sync is
turned on later, its full history has correct provenance for conflict
resolution.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path


def _config_dir() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home) if config_home else Path.home() / ".config"
    d = base / "tudo"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_device_id() -> str:
    path = _config_dir() / "device_id"
    if path.exists():
        value = path.read_text().strip()
        if value:
            return value

    value = str(uuid.uuid4())
    path.write_text(value + "\n")
    return value
