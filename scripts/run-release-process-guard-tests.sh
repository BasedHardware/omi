#!/usr/bin/env bash
# Run the release-process guard pytest self-suite with the repository's locked
# backend environment (pytest is a locked backend dependency).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=dev-harness/_resolve_python.sh
source "$ROOT_DIR/scripts/dev-harness/_resolve_python.sh"

BACKEND_PYTHON="$(dev_harness_ensure_python_with pytest)"

exec "$BACKEND_PYTHON" -m pytest -q "$ROOT_DIR/.github/scripts/test_check_release_process_guards.py"
