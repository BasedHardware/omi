#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
PYTHONPATH="scripts/dev-harness${PYTHONPATH:+:$PYTHONPATH}" python3 -m dev_harness.cli logs
