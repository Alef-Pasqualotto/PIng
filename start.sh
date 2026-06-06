#!/usr/bin/env bash
# start.sh — sets up the environment and launches the attendance app.
#
# Usage:
#   bash start.sh          # normal start
#   bash start.sh --reset  # wipe the database before starting

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VENV_DIR=".venv"
REQUIREMENTS="requirements.txt"
DB_FILE="attendance.db"
HOST="0.0.0.0"
PORT="8000"

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"

info()    { echo -e "${GREEN}[start]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[warn]${RESET}  $*"; }
error()   { echo -e "${RED}[error]${RESET} $*"; exit 1; }

# ---------------------------------------------------------------------------
# --reset flag
# ---------------------------------------------------------------------------

if [[ "${1:-}" == "--reset" ]]; then
    if [[ -f "$DB_FILE" ]]; then
        warn "Deleting existing database: $DB_FILE"
        rm "$DB_FILE"
    else
        info "No database found, nothing to reset."
    fi
fi

# ---------------------------------------------------------------------------
# Python check
# ---------------------------------------------------------------------------

if ! command -v python3 &>/dev/null; then
    error "python3 not found. Please install Python 3.10 or newer."
fi

PYTHON_VERSION=$(python3 -c "import sys; print(sys.version_info.minor)")
if [[ "$PYTHON_VERSION" -lt 10 ]]; then
    error "Python 3.10+ is required (found 3.${PYTHON_VERSION})."
fi

# ---------------------------------------------------------------------------
# Virtual environment
# ---------------------------------------------------------------------------

if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate
source "$VENV_DIR/bin/activate"

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

if [[ ! -f "$REQUIREMENTS" ]]; then
    error "$REQUIREMENTS not found. Cannot install dependencies."
fi

info "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r "$REQUIREMENTS"

# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

info "Starting attendance app on ${HOST}:${PORT} ..."
echo ""

exec uvicorn main:app --host "$HOST" --port "$PORT"