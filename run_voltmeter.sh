#!/bin/bash
# Start the GUI with the Python interpreter from this project's virtualenv.

set -u

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG_FILE="$PROJECT_DIR/launcher.log"

if [ ! -x "$VENV_PYTHON" ]; then
    MESSAGE="Virtual environment not found. Run: bash $PROJECT_DIR/setup.sh"
    if command -v notify-send >/dev/null 2>&1; then
        notify-send "PyQt Voltmeter" "$MESSAGE"
    fi
    echo "$MESSAGE" >&2
    exit 1
fi

cd "$PROJECT_DIR"
exec "$VENV_PYTHON" "$PROJECT_DIR/main.py" >>"$LOG_FILE" 2>&1
