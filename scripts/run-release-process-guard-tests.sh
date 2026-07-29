#!/usr/bin/env bash
# Run the release-process guard self-tests with the repository's locked PyYAML dependency.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PYTHON="$ROOT_DIR/backend/.venv/bin/python"

if [[ ! -x "$BACKEND_PYTHON" ]] || ! "$BACKEND_PYTHON" -c "import yaml"; then
  "$ROOT_DIR/backend/scripts/sync-python-deps.sh"
fi

# pytest exits 5 when it collects nothing, so an emptied suite fails instead of passing silently.
exec "$BACKEND_PYTHON" -m pytest "$ROOT_DIR/.github/scripts/test_check_release_process_guards.py" -q "$@"
