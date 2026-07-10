#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=_source_local_dev_env.sh
source "$(dirname "$0")/_source_local_dev_env.sh"
cd "$(dirname "$0")/../.."
PYTHON_BIN="${PYTHON:-backend/venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi
PYTHONPATH="scripts/dev-harness${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m dev_harness.cli logs
