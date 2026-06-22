#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
PYTHON_BIN="${PYTHON:-backend/venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi
PYTHONPATH="scripts/dev-harness${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m dev_harness.cli summary
