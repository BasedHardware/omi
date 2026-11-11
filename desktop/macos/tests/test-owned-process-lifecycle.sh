#!/usr/bin/env bash
# Synthetic owned-process lifecycle regressions for the fault-flow supervisor.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -m unittest "$SCRIPT_DIR/test_owned_process.py"
