#!/usr/bin/env bash
# Turns on syncing with a tudo server.
#
# Asks for the server address (e.g. "127.0.0.1:8000" or "tudo.jsezar.ir"),
# normalizes it into a base API URL (appending /api/), optionally asks for
# an API key, verifies connectivity, and installs a periodic background
# sync job (systemd --user timer, falling back to cron) that runs every 5
# minutes. Run disconnect_server.sh to undo all of this.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Figure out which installation (and therefore which python) to use ----
if [ -x "/opt/tudo/venv/bin/python" ]; then
    PYTHON_BIN="/opt/tudo/venv/bin/python"
    SRC_DIR="/opt/tudo/src"
elif [ -x "$HOME/.local/share/tudo/app/venv/bin/python" ]; then
    PYTHON_BIN="$HOME/.local/share/tudo/app/venv/bin/python"
    SRC_DIR="$HOME/.local/share/tudo/app/src"
elif [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    # Running from a source checkout without having run install.sh yet.
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
    SRC_DIR="$SCRIPT_DIR/src"
else
    echo "Error: could not find a tudo installation (looked for /opt/tudo, ~/.local/share/tudo/app, and $SCRIPT_DIR/.venv)." >&2
    echo "Run ./install.sh first." >&2
    exit 1
fi

echo "tudo sync setup"
echo "==============="
echo

read -r -p "Server address (e.g. 127.0.0.1:8000 or your-domain.com): " RAW_INPUT
if [ -z "$RAW_INPUT" ]; then
    echo "Error: server address is required." >&2
    exit 1
fi

# Strip trailing slashes.
INPUT="${RAW_INPUT%/}"

if [[ "$INPUT" == http://* || "$INPUT" == https://* ]]; then
    BASE_URL="$INPUT"
else
    case "$INPUT" in
        127.*|localhost|localhost:*)
            BASE_URL="http://$INPUT"
            ;;
        *)
            BASE_URL="https://$INPUT"
            ;;
    esac
fi
SERVER_URL="$BASE_URL/api/"

read -r -s -p "API key (press Enter to skip): " API_KEY
echo

echo
echo "Checking connectivity to $SERVER_URL ..."
HEALTH_URL="${BASE_URL}/api/health"
if curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; then
    echo "Server reachable."
else
    echo "Warning: could not reach $HEALTH_URL." >&2
    echo "Saving the configuration anyway - syncing will start working once the server is reachable." >&2
fi
echo

# --- Save the sync configuration -------------------------------------------
"$PYTHON_BIN" - "$SERVER_URL" "$API_KEY" <<PYEOF
import sys
sys.path.insert(0, "$SRC_DIR")
import sync_config

server_url, api_key = sys.argv[1], sys.argv[2]
config = sync_config.load_config()
config.update(
    enabled=True,
    server_url=server_url,
    api_key=api_key or None,
)
sync_config.save_config(config)
print(f"Saved sync config -> {sync_config.config_path()}")
PYEOF

# --- Install a periodic background sync (every 5 minutes) ------------------
SYNC_CMD="$PYTHON_BIN $SRC_DIR/sync_worker.py sync"

SCHEDULED=0

if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    UNIT_DIR="$HOME/.config/systemd/user"
    mkdir -p "$UNIT_DIR"

    cat > "$UNIT_DIR/tudo-sync.service" <<EOF
[Unit]
Description=tudo background sync

[Service]
Type=oneshot
ExecStart=$SYNC_CMD
EOF

    cat > "$UNIT_DIR/tudo-sync.timer" <<'EOF'
[Unit]
Description=Run tudo sync every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target
EOF

    if systemctl --user daemon-reload 2>/dev/null && systemctl --user enable --now tudo-sync.timer 2>/dev/null; then
        echo "Installed a systemd --user timer: syncing will run every 5 minutes in the background."
        SCHEDULED=1
    else
        echo "Warning: found systemd but could not enable a --user timer (this can happen without a" >&2
        echo "full login session, e.g. in some containers). Falling back to cron if available." >&2
        rm -f "$UNIT_DIR/tudo-sync.service" "$UNIT_DIR/tudo-sync.timer"
    fi
fi

if [ "$SCHEDULED" -eq 0 ] && command -v crontab >/dev/null 2>&1; then
    MARKER="# tudo-sync (managed by connect_to_server.sh)"
    NEW_LINE="*/5 * * * * $SYNC_CMD >/dev/null 2>&1 $MARKER"
    if ( crontab -l 2>/dev/null | grep -vF "$MARKER" ; echo "$NEW_LINE" ) | crontab - 2>/dev/null; then
        echo "Installed a cron job: syncing will run every 5 minutes in the background."
        SCHEDULED=1
    fi
fi

if [ "$SCHEDULED" -eq 0 ]; then
    echo "Warning: could not set up a periodic background sync (no usable systemd --user or cron)." >&2
    echo "Syncing will still happen right after each change, and opportunistically" >&2
    echo "when you use tudo/todo/idea. Run '$SYNC_CMD' manually if needed." >&2
fi

echo
echo "Running an initial sync..."
if "$PYTHON_BIN" "$SRC_DIR/sync_worker.py" sync; then
    echo "Sync is enabled and working."
else
    echo "Sync is enabled, but the initial attempt failed (this is fine - it will keep trying)."
fi

echo
echo "Done! Syncing is now active. Run ./disconnect_server.sh to turn it off."
