#!/usr/bin/env bash
# Refresh the backend uv pylock from the human-maintained requirements files.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_VERSION="$(tr -d '[:space:]' < .python-version)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

uv python install "$PYTHON_VERSION"
uv pip compile \
  requirements.txt \
  testing/e2e/requirements.txt \
  --format pylock.toml \
  --python "$PYTHON_VERSION" \
  --output-file pylock.toml \
  --custom-compile-command 'backend/scripts/update-python-lock.sh'
