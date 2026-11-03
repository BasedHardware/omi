#!/usr/bin/env bash
# Pinned Flutter + prepared hermetic app inputs are prerequisites (bash app/test.sh).
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$APP_DIR/tool/perf_shell.py" --check
exec python3 "$APP_DIR/tool/perf_gate_runner.py" "$@"
