#!/usr/bin/env bash
# Run release-process guards with the repository's locked PyYAML dependency,
# then the focused backend behavioral test for the qualification guard.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=dev-harness/_resolve_python.sh
source "$ROOT_DIR/scripts/dev-harness/_resolve_python.sh"

BACKEND_PYTHON="$(dev_harness_ensure_python_with yaml)"

# The guard's behavioral contract lives in the backend unit suite (it executes
# check_desktop_qualification_runner against a mutated promotion workflow). Run
# it here so a guard-only diff cannot weaken the trusted-repository gate without
# exercising the mutation test.
"$BACKEND_PYTHON" -m pytest -q "$ROOT_DIR/backend/tests/unit/test_desktop_release_scripts.py::test_release_process_guard_matches_trusted_auto_promotion"

exec "$BACKEND_PYTHON" "$ROOT_DIR/.github/scripts/check-release-process-guards.py" "$@"
