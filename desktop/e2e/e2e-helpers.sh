#!/usr/bin/env bash
# Shared helpers for agent-swift E2E flows on the Omi desktop app.
# Source this at the top of each flow script.

set -euo pipefail

# --- Config ---
export SCREENSHOT_DIR="${E2E_SCREENSHOT_DIR:-/tmp/omi-desktop-e2e}"
FLOW_NAME=""
STEP_NUM=0
PASS_COUNT=0
FAIL_COUNT=0
FAILURES=""

BUNDLE_ID="${E2E_BUNDLE_ID:-com.omi.desktop-dev}"

# agent-swift binary — override via AGENT_SWIFT env var
AGENT_SWIFT="${AGENT_SWIFT:-agent-swift}"

# --- Core helpers ---

as() {
  local output rc=0
  output=$($AGENT_SWIFT "$@" 2>&1) || rc=$?
  printf '%s\n' "$output"
  return $rc
}

as_wait() {
  sleep "${1:-${E2E_WAIT:-0.5}}"
}

# --- Setup / teardown ---

e2e_setup() {
  FLOW_NAME="$1"
  STEP_NUM=0
  PASS_COUNT=0
  FAIL_COUNT=0
  FAILURES=""
  mkdir -p "$SCREENSHOT_DIR"

  echo ""
  echo "=== E2E: $FLOW_NAME ==="
  echo ""

  # Check doctor
  if ! $AGENT_SWIFT doctor 2>/dev/null | grep -q "Accessibility.*OK\|granted"; then
    echo "[setup] WARNING: Accessibility permission may not be granted"
  fi

  # Connect to app
  local status
  status=$($AGENT_SWIFT status --json 2>/dev/null || echo '{"connected":false}')
  if printf '%s' "$status" | python3 -c "import sys,json; sys.exit(0 if json.load(sys.stdin).get('connected') else 1)" 2>/dev/null; then
    echo "[setup] Already connected"
  else
    echo "[setup] Connecting to $BUNDLE_ID..."
    $AGENT_SWIFT connect --bundle-id "$BUNDLE_ID" 2>&1 || { echo "[setup] Could not connect"; return 1; }
  fi

  # Health check
  local count
  count=$($AGENT_SWIFT snapshot -i --json 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
  if [ "$count" -ge 3 ]; then
    echo "[setup] Ready ($count interactive elements)"
  else
    echo "[setup] App may not be fully loaded ($count elements)"
  fi
}

e2e_teardown() {
  echo ""
  echo "=== $FLOW_NAME: $PASS_COUNT passed, $FAIL_COUNT failed ==="
  if [ "$FAIL_COUNT" -gt 0 ]; then
    echo "FAILURES:$FAILURES"
    return 1
  fi
  return 0
}

e2e_step() {
  STEP_NUM=$((STEP_NUM + 1))
  echo ""
  echo "--- Step $STEP_NUM: $1 ---"
}

e2e_pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  echo "[PASS] ${1:-Step $STEP_NUM}"
}

e2e_fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  local msg="${1:-Step $STEP_NUM}"
  FAILURES="$FAILURES"$'\n'"  - $msg"
  echo "[FAIL] $msg"
}

# --- Snapshot helpers ---

as_snapshot_count() {
  as snapshot --json 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))"
}

as_snapshot_interactive_count() {
  as snapshot -i --json 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))"
}

as_find_role() {
  local role="$1"
  as find role "$role" --json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('ref',''))"
}

as_find_text() {
  local text="$1"
  as find text "$text" --json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('ref',''))"
}

as_find_label() {
  local label="$1"
  local index="${2:-0}"
  as snapshot -i --json 2>/dev/null | python3 -c "
import sys, json
matches = [e for e in json.load(sys.stdin) if '$label' in (e.get('label') or '')]
if len(matches) > $index: print(matches[$index]['ref'])
else: sys.exit(1)
"
}

# Assert helpers
as_is() {
  local condition="$1" ref="$2"
  as is "$condition" "@$ref" 2>/dev/null
}

as_wait_text() {
  local text="$1"
  local timeout="${2:-5000}"
  as wait text "$text" --timeout "$timeout" 2>/dev/null
}

as_wait_exists() {
  local ref="$1"
  local timeout="${2:-5000}"
  as wait exists "@$ref" --timeout "$timeout" 2>/dev/null
}

# Screenshot via agent-swift (captures app window only)
as_screenshot() {
  if [ "${E2E_FAST:-}" = "1" ]; then return 0; fi
  local name="$1"
  local path="$SCREENSHOT_DIR/${FLOW_NAME}-${STEP_NUM}-${name}.png"
  as screenshot "$path" 2>&1 || true
  echo "  Screenshot: $path"
}

# --- Navigation helpers ---

as_click_wait() {
  as click "@$1" 2>&1
  as_wait
}

as_press_wait() {
  as press "@$1" 2>&1
  as_wait
}

as_click_label() {
  local label="$1"
  local ref
  ref=$(as_find_label "$label") || { echo "  Could not find element with label: $label"; return 1; }
  echo "  Found '$label' at $ref"
  as click "@$ref" 2>&1
  as_wait
}

as_press_label() {
  local label="$1"
  local ref
  ref=$(as_find_label "$label") || { echo "  Could not find element with label: $label"; return 1; }
  echo "  Found '$label' at $ref"
  as press "@$ref" 2>&1
  as_wait
}
