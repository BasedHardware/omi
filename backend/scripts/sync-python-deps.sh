#!/usr/bin/env bash
# Sync the backend local virtualenv from the checked-in uv.lock.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_VERSION="$(tr -d '[:space:]' < .python-version)"
VENV_PATH="${VENV_PATH:-.venv}"

if [[ ! -f uv.lock ]]; then
  echo "Expected dependency lock uv.lock in $ROOT_DIR, but it was not found." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

uv python install "$PYTHON_VERSION"
UV_PROJECT_ENVIRONMENT="$VENV_PATH" uv sync --frozen --python "$PYTHON_VERSION"

echo "Backend dependencies synced from uv.lock into $ROOT_DIR/$VENV_PATH"
