#!/usr/bin/env bash
# Run release-process guards with the repository's locked PyYAML dependency,
# then the focused backend behavioral test for the qualification guard.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=dev-harness/_resolve_python.sh
source "$ROOT_DIR/scripts/dev-harness/_resolve_python.sh"

if ! BACKEND_PYTHON="$(dev_harness_canonical_python)" \
  || ! "$BACKEND_PYTHON" -c "import yaml" >/dev/null 2>&1; then
  "$ROOT_DIR/backend/scripts/sync-python-deps.sh"
  if ! BACKEND_PYTHON="$(dev_harness_canonical_python)"; then
    echo "FAIL: dependency sync did not create the canonical backend/.venv interpreter." >&2
    exit 1
  fi
fi

# The guard's behavioral contract lives in the backend unit suite (it executes
# check_desktop_qualification_runner against a mutated promotion workflow). Run
# it here so a guard-only diff cannot weaken the trusted-repository gate without
# exercising the mutation test.
"$BACKEND_PYTHON" -m pytest -q "$ROOT_DIR/backend/tests/unit/test_desktop_release_scripts.py"

exec "$BACKEND_PYTHON" "$ROOT_DIR/.github/scripts/check-release-process-guards.py" "$@"
