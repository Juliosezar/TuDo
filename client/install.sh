#!/usr/bin/env bash
# Installer for tudo.
#
# Installs three commands:
#   tudo  - shows the dashboard (system, network, todos, ideas)
#   todo  - manage todos directly
#   idea  - manage ideas directly
#
# By default installs for the current user only (no root required):
#   App files under:  ~/.local/share/tudo/app
#   Commands under:   ~/.local/bin
#
# Pass --system (and run with sudo/root) to install machine-wide instead:
#   App files under:  /opt/tudo
#   Commands under:   /usr/local/bin
#
# The sqlite database used by the app always lives at
# ~/.local/share/tudo/tudo.db (per user), regardless of install mode.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/src"
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"

SYSTEM_INSTALL=0

for arg in "$@"; do
    case "$arg" in
        --system)
            SYSTEM_INSTALL=1
            ;;
        -h|--help)
            cat <<'EOF'
Usage: ./install.sh [--system]

  (no flags)   Install for the current user under ~/.local/share/tudo/app
               and place launcher scripts in ~/.local/bin.

  --system     Install system-wide under /opt/tudo (requires root) and
               place launcher scripts in /usr/local/bin.
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
        echo "Error: --system install requires root. Try: sudo ./install.sh --system" >&2
        exit 1
    fi
    INSTALL_DIR="/opt/tudo"
    BIN_DIR="/usr/local/bin"
else
    INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/tudo/app"
    BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
fi

echo "Installing tudo"
echo "  App files: $INSTALL_DIR"
echo "  Commands:  $BIN_DIR/{tudo,todo,idea}"
echo

# --- 1. Check for a suitable python3 ---------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 is required but was not found in PATH." >&2
    exit 1
fi

PYTHON_VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PYTHON_MAJOR="${PYTHON_VERSION%%.*}"
PYTHON_MINOR="${PYTHON_VERSION##*.}"
if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
    echo "Error: Python 3.10+ is required (found $PYTHON_VERSION)." >&2
    exit 1
fi

# --- 2. Copy the application source -----------------------------------------
mkdir -p "$INSTALL_DIR"
rm -rf "$INSTALL_DIR/src"
cp -r "$SRC_DIR" "$INSTALL_DIR/src"

# --- 3. Create/refresh the virtual environment ------------------------------
if [ ! -d "$INSTALL_DIR/venv" ]; then
    echo "Creating virtual environment..."
    if ! python3 -m venv "$INSTALL_DIR/venv"; then
        echo "Error: failed to create a virtual environment." >&2
        echo "On Debian/Ubuntu, try: sudo apt install python3-venv" >&2
        exit 1
    fi
fi

echo "Installing dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip --quiet
"$INSTALL_DIR/venv/bin/pip" install -r "$REQUIREMENTS_FILE" --quiet

# --- 4. Install launcher scripts ---------------------------------------------
mkdir -p "$BIN_DIR"

write_launcher() {
    local name="$1" entry="$2"
    local target="$BIN_DIR/$name"
    cat > "$target" <<LAUNCHER
#!/usr/bin/env bash
exec "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/src/$entry" "\$@"
LAUNCHER
    chmod +x "$target"
}

write_launcher tudo main.py
write_launcher todo todo_entry.py
write_launcher idea idea_entry.py

echo "Installed commands: tudo, todo, idea"
echo

# --- 5. Make sure BIN_DIR is on PATH ----------------------------------------
# Added to both ~/.bashrc and ~/.zshrc (regardless of which shell is
# currently active), so `tudo`/`todo`/`idea` work no matter which shell you
# end up using.
if [ "$SYSTEM_INSTALL" -eq 0 ]; then
    LINE="export PATH=\"$BIN_DIR:\$PATH\""

    for SHELL_RC in "$HOME/.bashrc" "$HOME/.zshrc"; do
        if [ -f "$SHELL_RC" ] && grep -Fq "$LINE" "$SHELL_RC" 2>/dev/null; then
            echo "PATH entry already present in $SHELL_RC."
        else
            {
                echo ""
                echo "# Added by the tudo installer"
                echo "$LINE"
            } >> "$SHELL_RC"
            echo "Added $BIN_DIR to PATH in $SHELL_RC."
        fi
    done

    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *) echo "Restart your shell (or run 'source ~/.bashrc'/'source ~/.zshrc') to use tudo/todo/idea now." ;;
    esac
else
    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *) echo "Note: $BIN_DIR is not currently in your PATH. Add it manually (it usually already is for a system install)." ;;
    esac
fi

echo
echo "Done! Try running: tudo"
