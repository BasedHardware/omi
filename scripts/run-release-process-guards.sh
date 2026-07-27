#!/usr/bin/env bash
# Run release-process guards with the repository's locked PyYAML dependency.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PYTHON="$ROOT_DIR/backend/.venv/bin/python"

if [[ ! -x "$BACKEND_PYTHON" ]] || ! "$BACKEND_PYTHON" -c "import yaml"; then
  "$ROOT_DIR/backend/scripts/sync-python-deps.sh"
fi

exec "$BACKEND_PYTHON" "$ROOT_DIR/.github/scripts/check-release-process-guards.py" "$@"
