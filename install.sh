#!/usr/bin/env bash
#
# install.sh -- set up the Unohana Visualizer for the current user.
#
# Creates a local virtualenv, installs the Python dependencies, and drops a
# user-level `unohana-visualizer` launcher into ~/.local/bin so the app can
# be started with a single command from anywhere (no sudo required).
#
# Usage:
#     ./install.sh            # install/update everything
#     ./install.sh --force    # rebuild the virtualenv from scratch
#     ./install.sh --uninstall  # remove the launcher (keeps code + .venv)
#
# After installing, make sure ~/.local/bin is on your PATH (most distros
# have it by default):
#
#     echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

set -euo pipefail

APP_NAME="unohana-visualizer"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/.venv"
LAUNCHER_DIR="$HOME/.local/bin"
LAUNCHER="$LAUNCHER_DIR/$APP_NAME"
FORCE=0
UNINSTALL=0

for arg in "$@"; do
    case "$arg" in
        --force)    FORCE=1 ;;
        --uninstall) UNINSTALL=1 ;;
        -h|--help)
            sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "error: unknown option: $arg (try --help)" >&2
            exit 1
            ;;
    esac
done

# --- Uninstall path -----------------------------------------------------------
if [[ $UNINSTALL -eq 1 ]]; then
    if [[ -e "$LAUNCHER" ]]; then
        rm -f "$LAUNCHER"
        echo "Removed $LAUNCHER"
    else
        echo "Nothing to do: no $LAUNCHER launcher found."
    fi
    exit 0
fi

# --- Sanity checks ------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    echo "error: python3 not found on PATH. Install Python 3 first." >&2
    exit 1
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
    echo "error: Python 3.8+ is required (found: $(python3 --version 2>&1))." >&2
    exit 1
fi

echo "==> Project directory: $HERE"

# --- Virtualenv ----------------------------------------------------------------
if [[ $FORCE -eq 1 && -d "$VENV" ]]; then
    echo "==> --force: removing existing virtualenv"
    rm -rf "$VENV"
fi

if [[ ! -d "$VENV" ]]; then
    echo "==> Creating virtualenv at $VENV"
    python3 -m venv "$VENV"
else
    echo "==> Reusing existing virtualenv at $VENV"
fi

# --- Dependencies ---------------------------------------------------------------
echo "==> Installing Python requirements"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$HERE/requirements.txt"

# --- Launcher -------------------------------------------------------------------
echo "==> Installing launcher to $LAUNCHER"
mkdir -p "$LAUNCHER_DIR"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
# Unohana Visualizer launcher (installed by install.sh).
# Starts the audio-reactive blood-drip overlay on top of the wallpaper.
# Optional argument: path to an alternate config.json.
set -euo pipefail
exec "$VENV/bin/python" "$HERE/main.py" "\$@"
EOF
chmod +x "$LAUNCHER"

# --- PATH check -----------------------------------------------------------------
if [[ -n "${PATH:-}" ]] && [[ ":$PATH:" != *":$LAUNCHER_DIR:"* ]]; then
    echo
    echo "note: $LAUNCHER_DIR is not on your PATH. Add it to your shell rc, e.g.:"
    echo "    echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
    echo
fi

echo "==> Done! Launch the visualizer with:"
echo
echo "    $APP_NAME              # with the default config.json"
echo "    $APP_NAME /path/to/config.json"
echo
echo "    Stop it with Ctrl+C."
echo
echo "    Tip: set unohana.jpg as your wallpaper first, e.g.:"
echo "    feh --bg-scale '$HERE/unohana.jpg'"
echo
echo "    Uninstall the launcher later with: ./install.sh --uninstall"
