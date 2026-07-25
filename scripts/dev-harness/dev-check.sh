#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=_source_local_dev_env.sh
source "$(dirname "$0")/_source_local_dev_env.sh"
# shellcheck source=_resolve_python.sh
source "$(dirname "$0")/_resolve_python.sh"
cd "$(dirname "$0")/../.."
if git ls-files --error-unmatch backend/.env.local-dev >/dev/null 2>&1; then
  echo "backend/.env.local-dev is tracked by git — remove it from the index before committing secrets" >&2
  exit 1
fi
PYTHON_BIN="$(dev_harness_python)"
PYTHONPATH="scripts/dev-harness${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m dev_harness.cli check
