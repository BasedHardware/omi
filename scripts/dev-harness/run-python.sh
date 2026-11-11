#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_resolve_python.sh
source "$SCRIPT_DIR/_resolve_python.sh"

PYTHON_BIN="$(dev_harness_python)"
exec "$PYTHON_BIN" "$@"
