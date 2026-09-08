#!/bin/bash
# Keep the Python development-loop contract test in the desktop test runner's
# test-*.sh discovery path.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$SCRIPT_DIR/test-dev-feedback.py"
