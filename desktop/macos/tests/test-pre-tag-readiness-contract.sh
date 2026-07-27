#!/usr/bin/env bash
# Static contract for the trusted-M1 pre-tag readiness lifecycle. The actual
# harness is deliberately exercised only by the trusted runner; this prevents
# workflow/script drift from creating a tag without ownership-scoped cleanup.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
READINESS="$SCRIPT_DIR/../scripts/pre-tag-readiness.sh"

require_text() {
  local needle="$1"
  grep -Fq -- "$needle" "$READINESS" || {
    echo "FAIL: pre-tag readiness contract missing: $needle" >&2
    exit 1
  }
}

require_order() {
  python3 - "$READINESS" "$@" <<'PY'
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
position = -1
for needle in sys.argv[2:]:
    next_position = text.find(needle, position + 1)
    if next_position < 0:
        raise SystemExit(f"FAIL: missing ordered readiness fragment: {needle}")
    position = next_position
PY
}

# Cache and qualification leases are independently authenticated capabilities.
require_text '"$CACHE_COMMAND" prepare'
require_text '"$SOURCE_SHA" "$SOURCE_REPOSITORY" "$CACHE_LEASE_ID" "$$"'
require_text '"$LEASE_COMMAND" acquire'
require_text '"$WORKTREE" "$READINESS_LEASE_ID" "$$" "$PORT_OFFSET" "$RETAINED_RUNS"'
require_text '"$LEASE_COMMAND" release'
require_text '"$CACHE_COMMAND" release'
require_text 'OMI_QUALIFICATION_LEASE_ROOT="$LEASE_ROOT"'
require_text 'OMI_LOCAL_STATE_ROOT="$LEASE_ROOT/state"'
require_text 'OMI_LOCAL_INSTANCE="$READINESS_LEASE_ID"'
require_text 'OMI_HARNESS_PORT_OFFSET="$PORT_OFFSET"'
require_text 'OMI_HARNESS_OWNERSHIP_TOKEN="$READINESS_LEASE_TOKEN"'
require_text 'desktop-core-harness.sh --readiness'

# A foreign/unproven listener must cause authenticated cleanup to fail closed:
# no broad process control, no passing receipt, and retained lease evidence.
require_text 'emit_evidence false'
require_text 'READINESS_CLEANUP_OK=1'
require_text 'if [[ "$READINESS_COMPLETE" -eq 1 && "$READINESS_CLEANUP_OK" -ne 1 ]]'
require_order \
  '"$LEASE_COMMAND" acquire' \
  'desktop-core-harness.sh --readiness' \
  'READINESS_COMPLETE=1'
require_order \
  '"$LEASE_COMMAND" release' \
  '"$CACHE_COMMAND" release' \
  'READINESS_CLEANUP_OK=1' \
  'emit_evidence true'
if grep -Eq 'pkill|osascript|killall|lsof.*kill|ps .*kill|kill -[0-9A-Z]+' "$READINESS"; then
  echo "FAIL: readiness must not use broad process control" >&2
  exit 1
fi

echo "pre-tag readiness contract tests passed"
