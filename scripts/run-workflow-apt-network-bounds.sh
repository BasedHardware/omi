#!/usr/bin/env bash
# Run the apt-network-bounds guard and its self-test with the repository's locked
# PyYAML dependency. Bare python3 on a hosted runner has no PyYAML, so resolve the
# canonical backend interpreter the same way the release-process guards do.
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

# The self-test includes a case that runs the guard across every workflow in the
# tree, so this single entry point is both the proof and the enforcement.
exec "$BACKEND_PYTHON" "$ROOT_DIR/.github/scripts/test_check_workflow_apt_network_bounds.py" "$@"
