#!/usr/bin/env bash
# Refresh the backend uv.lock from pyproject.toml.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_VERSION="$(tr -d '[:space:]' < .python-version)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

uv python install "$PYTHON_VERSION"

lock_cmd=(uv lock --python "$PYTHON_VERSION")
if [[ "${UV_UPGRADE:-${PYLOCK_UPGRADE:-0}}" == "1" ]]; then
  lock_cmd+=(--upgrade)
fi

"${lock_cmd[@]}"

echo "Backend uv.lock refreshed (python $PYTHON_VERSION)"
