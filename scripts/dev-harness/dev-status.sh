#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=_source_local_dev_env.sh
source "$(dirname "$0")/_source_local_dev_env.sh"
# shellcheck source=_resolve_python.sh
source "$(dirname "$0")/_resolve_python.sh"
cd "$(dirname "$0")/../.."
PYTHON_BIN="$(dev_harness_python)"
PYTHONPATH="$(dev_harness_pythonpath "$PYTHON_BIN" scripts/dev-harness)" "$PYTHON_BIN" -m dev_harness.cli status
