#!/usr/bin/env bash
# Turns off syncing: removes the periodic background sync job and the local
# sync configuration. Your local todos/ideas and the server's data are left
# untouched - this only stops *this device* from syncing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -x "/opt/tudo/venv/bin/python" ]; then
    PYTHON_BIN="/opt/tudo/venv/bin/python"
    SRC_DIR="/opt/tudo/src"
elif [ -x "$HOME/.local/share/tudo/app/venv/bin/python" ]; then
    PYTHON_BIN="$HOME/.local/share/tudo/app/venv/bin/python"
    SRC_DIR="$HOME/.local/share/tudo/app/src"
elif [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
    SRC_DIR="$SCRIPT_DIR/src"
else
    PYTHON_BIN=""
    SRC_DIR=""
fi

# --- Remove the periodic background sync job --------------------------------
if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    if systemctl --user list-unit-files tudo-sync.timer >/dev/null 2>&1; then
        systemctl --user disable --now tudo-sync.timer 2>/dev/null || true
        rm -f "$HOME/.config/systemd/user/tudo-sync.service" "$HOME/.config/systemd/user/tudo-sync.timer"
        systemctl --user daemon-reload 2>/dev/null || true
        echo "Removed the systemd --user sync timer."
    fi
fi

if command -v crontab >/dev/null 2>&1; then
    MARKER="# tudo-sync (managed by connect_to_server.sh)"
    if crontab -l 2>/dev/null | grep -qF "$MARKER"; then
        ( crontab -l 2>/dev/null | grep -vF "$MARKER" ) | crontab - || true
        echo "Removed the cron sync job."
    fi
fi

# --- Remove the local sync configuration ------------------------------------
if [ -n "$PYTHON_BIN" ]; then
    "$PYTHON_BIN" - <<PYEOF
import sys
sys.path.insert(0, "$SRC_DIR")
import sync_config
sync_config.disable()
print(f"Removed sync config -> {sync_config.config_path()}")
PYEOF
else
    rm -f "$HOME/.config/tudo/sync.json"
fi

echo
echo "Done. Syncing is now disabled. Your local todos/ideas are untouched,"
echo "and nothing was removed from the server."
