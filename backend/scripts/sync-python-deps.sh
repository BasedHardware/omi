#!/usr/bin/env bash
# Sync the backend local virtualenv from the checked-in uv pylock.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_VERSION="$(tr -d '[:space:]' < .python-version)"
VENV_PATH="${VENV_PATH:-.venv}"
LOCK_FILE="pylock.toml"
PYTHON_BIN="$VENV_PATH/bin/python"

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64|Darwin-aarch64)
    LOCK_FILE="pylock.macos.toml"
    ;;
  Darwin-x86_64|Darwin-amd64)
    LOCK_FILE="pylock.macos-x86_64.toml"
    ;;
  MINGW*-x86_64|MSYS*-x86_64|CYGWIN*-x86_64)
    LOCK_FILE="pylock.windows.toml"
    PYTHON_BIN="$VENV_PATH/Scripts/python.exe"
    ;;
esac

if [[ ! -f "$LOCK_FILE" ]]; then
  echo "Expected dependency lock $LOCK_FILE for platform $(uname -s)-$(uname -m), but it was not found." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

uv python install "$PYTHON_VERSION"
uv venv --allow-existing --python "$PYTHON_VERSION" "$VENV_PATH"
uv pip sync "$LOCK_FILE" --python "$PYTHON_BIN"

echo "Backend dependencies synced from $LOCK_FILE into $ROOT_DIR/$VENV_PATH"
