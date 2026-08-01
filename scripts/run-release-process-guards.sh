#!/usr/bin/env bash
# Run release-process guards with the repository's locked PyYAML dependency.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=dev-harness/_resolve_python.sh
source "$ROOT_DIR/scripts/dev-harness/_resolve_python.sh"

BACKEND_PYTHON="$(dev_harness_ensure_python_with yaml)"

exec "$BACKEND_PYTHON" "$ROOT_DIR/.github/scripts/check-release-process-guards.py" "$@"
