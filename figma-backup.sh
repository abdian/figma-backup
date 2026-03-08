#!/usr/bin/env bash
# Figma Backup -- launcher script
# Usage: ./figma-backup.sh [options]

set -uo pipefail
trap 'echo ""; echo "  [ERROR] Script failed."; read -rp "  Press Enter to close..." _' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# -- Find Python automatically --
find_python() {
    # 1) Try common commands in PATH
    for cmd in python3 python py; do
        if command -v "$cmd" &>/dev/null && "$cmd" --version &>/dev/null; then
            echo "$cmd"
            return
        fi
    done

    # 2) Search common Linux/macOS locations
    for p in /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
        if [ -x "$p" ] && "$p" --version &>/dev/null; then
            echo "$p"
            return
        fi
    done

    # 3) On Windows (Git Bash / MSYS2) -- search common install paths
    if [[ "${OS:-}" == "Windows_NT" ]] || [[ "$(uname -s)" == MINGW* ]] || [[ "$(uname -s)" == MSYS* ]]; then
        local appdata="${LOCALAPPDATA:-$USERPROFILE/AppData/Local}"
        # Convert backslashes for bash
        appdata="${appdata//\\//}"

        # Search Programs\Python
        for dir in "$appdata/Programs/Python"/Python3*/; do
            if [ -x "$dir/python.exe" ]; then
                echo "$dir/python.exe"
                return
            fi
        done

        # Search AppData\Local\Python
        for exe in "$appdata/Python"/*/python.exe "$appdata/Python/bin/python.exe"; do
            if [ -x "$exe" ]; then
                echo "$exe"
                return
            fi
        done

        # Search C:\Python
        for dir in /c/Python3*/; do
            if [ -x "$dir/python.exe" ]; then
                echo "$dir/python.exe"
                return
            fi
        done
    fi
}

PYTHON="$(find_python)"

if [ -z "$PYTHON" ]; then
    echo ""
    echo "  [ERROR] Python 3 is required but not found anywhere."
    echo "  Install it from https://www.python.org/downloads/"
    echo ""
    read -rp "  Press Enter to close..." _
    exit 1
fi

echo "  Found Python: $($PYTHON --version)"

# -- Create venv if it doesn't exist --
if [ ! -d ".venv" ]; then
    echo "  Setting up virtual environment..."
    "$PYTHON" -m venv .venv
fi

# -- Find venv python --
if [ -f ".venv/Scripts/python.exe" ]; then
    VENV_PYTHON=".venv/Scripts/python.exe"
elif [ -f ".venv/bin/python" ]; then
    VENV_PYTHON=".venv/bin/python"
else
    echo ""
    echo "  [ERROR] Virtual environment is broken. Delete .venv folder and try again."
    echo ""
    read -rp "  Press Enter to close..." _
    exit 1
fi

# -- Install/update dependencies --
"$VENV_PYTHON" -m pip install -q -r requirements.txt

# -- Check for .env file --
if [ ! -f ".env" ]; then
    echo ""
    echo "  [ERROR] No .env file found!"
    echo "  Copy .env.example to .env and fill in your values:"
    echo "    cp .env.example .env"
    echo ""
    read -rp "  Press Enter to close..." _
    exit 1
fi

# -- Run the tool --
"$VENV_PYTHON" -m figma_backup "$@"
