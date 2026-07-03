#!/usr/bin/env bash
# Uninstaller for tudo. Removes the app files and launcher commands installed
# by install.sh. By default your todos/ideas database
# (~/.local/share/tudo/tudo.db) is left untouched - you'll be asked whether
# to remove it too.
#
# Usage: ./uninstall.sh [--system] [--purge-data | --keep-data]

set -euo pipefail

SYSTEM_INSTALL=0
PURGE_DATA=""   # "", "yes", or "no" - "" means "ask interactively"
for arg in "$@"; do
    case "$arg" in
        --system) SYSTEM_INSTALL=1 ;;
        --purge-data) PURGE_DATA="yes" ;;
        --keep-data) PURGE_DATA="no" ;;
        -h|--help)
            cat <<'EOF'
Usage: ./uninstall.sh [--system] [--purge-data | --keep-data]

  --system       Uninstall the machine-wide install (under /opt/tudo),
                 requires root.
  --purge-data   Also delete the local todos/ideas database, without asking.
  --keep-data    Keep the local todos/ideas database, without asking.
  (default)      Ask interactively whether to delete the database.
EOF
            exit 0
            ;;
        *)
            echo "Unknown option: $arg" >&2
            exit 1
            ;;
    esac
done

if [ "$SYSTEM_INSTALL" -eq 1 ]; then
    if [ "$(id -u)" -ne 0 ]; then
        echo "Error: --system uninstall requires root. Try: sudo ./uninstall.sh --system" >&2
        exit 1
    fi
    INSTALL_DIR="/opt/tudo"
    BIN_DIR="/usr/local/bin"
else
    INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/tudo/app"
    BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
fi

echo "Removing $BIN_DIR/{tudo,todo,idea}..."
rm -f "$BIN_DIR/tudo" "$BIN_DIR/todo" "$BIN_DIR/idea"

echo "Removing $INSTALL_DIR..."
rm -rf "$INSTALL_DIR"

# The database always lives per-user, regardless of --system.
DB_PATH="${XDG_DATA_HOME:-$HOME/.local/share}/tudo/tudo.db"

if [ -f "$DB_PATH" ]; then
    if [ -z "$PURGE_DATA" ]; then
        if [ -t 0 ]; then
            read -r -p "Also delete your todos/ideas database at $DB_PATH? [y/N] " ANSWER
            case "$ANSWER" in
                [yY]|[yY][eE][sS]) PURGE_DATA="yes" ;;
                *) PURGE_DATA="no" ;;
            esac
        else
            echo "Note: not asking about $DB_PATH (no interactive terminal). Keeping it." >&2
            echo "Re-run with --purge-data to delete it non-interactively." >&2
            PURGE_DATA="no"
        fi
    fi

    if [ "$PURGE_DATA" = "yes" ]; then
        rm -f "$DB_PATH"
        echo "Deleted $DB_PATH."
    else
        echo "Keeping $DB_PATH."
    fi
else
    echo "No database found at $DB_PATH."
fi

echo
echo "Done."
