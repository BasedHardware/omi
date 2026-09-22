#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_SCRIPT="$MACOS_DIR/run.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

# The launcher may still use defaults for legitimate configuration, but it must
# never persist an unfiltered defaults dump or auth-state diagnostics. In
# particular, auth_idToken and auth_refreshToken are UserDefaults keys during
# the seed/migration window and must not enter a launcher-owned log.
python3 - "$RUN_SCRIPT" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
for marker in (
    "AUTH_DEBUG_LOG",
    "auth_debug",
    'defaults read "$BUNDLE_ID"',
    "grep -E 'auth_|hasCompleted|hasLaunched|currentTier|userShow'",
):
    if marker in text:
        raise SystemExit(f"forbidden auth diagnostic marker remains: {marker}")
PY

bash -n "$RUN_SCRIPT" || fail "run.sh is not valid bash"
echo "auth debug contract passed"
