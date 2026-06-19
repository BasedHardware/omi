#!/usr/bin/env bash
# Sync the backend local virtualenv from the checked-in uv pylock.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_VERSION="$(tr -d '[:space:]' < .python-version)"
VENV_PATH="${VENV_PATH:-.venv}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

uv python install "$PYTHON_VERSION"
uv venv --python "$PYTHON_VERSION" "$VENV_PATH"
uv pip sync pylock.toml --python "$VENV_PATH/bin/python"

echo "Backend dependencies synced into $ROOT_DIR/$VENV_PATH"
