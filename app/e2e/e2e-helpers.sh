#!/usr/bin/env bash
# Shared helpers for agent-flutter E2E flows.
# Source this at the top of each flow script.

set -euo pipefail

# --- Config ---
export SCREENSHOT_DIR="${E2E_SCREENSHOT_DIR:-/tmp/omi-e2e}"
FLOW_NAME=""
STEP_NUM=0
PASS_COUNT=0
FAIL_COUNT=0
FAILURES=""

# --- Recovery ---

DEVICE="${AGENT_FLUTTER_DEVICE:-emulator-5554}"
APP_PACKAGE="${E2E_APP_PACKAGE:-com.friend.ios.dev}"
APP_ACTIVITY="${E2E_APP_ACTIVITY:-${APP_PACKAGE}.MainActivity}"

# Bring app to foreground.
_foreground() {
  adb -s "$DEVICE" shell am start -n "${APP_PACKAGE}/${APP_ACTIVITY}" 2>/dev/null || true
  sleep 0.5
}

# Hot-restart the Flutter app to revive a dead Marionette isolate.
_hot_restart() {
  local flutter_pid
  flutter_pid=$(pgrep -f "flutter_tools.*run" | head -1 2>/dev/null || true)
  if [ -n "$flutter_pid" ]; then
    echo "  [recovery] Hot-restarting Flutter app..." >&2
    kill -SIGUSR2 "$flutter_pid" 2>/dev/null || true
    sleep 3
  fi
}

# Recovery: foreground → disconnect → reconnect.
_reconnect() {
  echo "  [recovery] Recovering Marionette connection..." >&2
  _foreground
  agent-flutter disconnect 2>/dev/null || true
  sleep 0.5
  agent-flutter connect 2>&1 >&2 || true
  sleep 0.5
}

# Check if the widget tree is healthy (>= 5 interactive elements).
_is_healthy() {
  local count
  count=$(agent-flutter snapshot -i --json 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
  [ "$count" -ge 5 ]
}

# Navigate to home tab by pressing the leftmost bottom nav InkWell.
_go_home() {
  agent-flutter snapshot -i --json 2>/dev/null | python3 -c "
import sys, json
elems = json.load(sys.stdin)
tabs = [e for e in elems if e.get('flutterType') == 'InkWell' and e['bounds']['y'] > 780]
if not tabs:
    # No nav bar visible — try back until we see one
    sys.exit(1)
tabs.sort(key=lambda e: e['bounds']['x'])
print(tabs[0]['ref'])
" 2>/dev/null > /tmp/_e2e_home_ref.txt || true
  if [ -s /tmp/_e2e_home_ref.txt ]; then
    agent-flutter press "@$(cat /tmp/_e2e_home_ref.txt)" 2>/dev/null || true
    sleep 0.3
  else
    # No nav bar — press back until we get one (max 3)
    for _ in 1 2 3; do
      agent-flutter back 2>/dev/null || true
      sleep 0.3
      if agent-flutter snapshot -i --json 2>/dev/null | python3 -c "
import sys, json
elems = json.load(sys.stdin)
tabs = [e for e in elems if e.get('flutterType') == 'InkWell' and e['bounds']['y'] > 780]
sys.exit(0 if tabs else 1)
" 2>/dev/null; then
        break
      fi
    done
  fi
}

# --- Core helpers ---

af() {
  local output rc=0
  output=$(agent-flutter "$@" 2>&1) || rc=$?
  if printf '%s' "$output" | grep -q "No isolate with Marionette"; then
    _reconnect
    rc=0
    output=$(agent-flutter "$@" 2>&1) || rc=$?
  fi
  printf '%s\n' "$output"
  return $rc
}

af_wait() {
  sleep "${1:-${E2E_WAIT:-0.3}}"
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

  # Ensure app is in foreground
  _foreground

  # Connect if needed
  local status
  status=$(agent-flutter status 2>/dev/null || echo '{"connected":false}')
  if printf '%s' "$status" | python3 -c "import sys,json; sys.exit(0 if json.load(sys.stdin).get('connected') else 1)" 2>/dev/null; then
    if _is_healthy; then
      echo "[setup] Ready"
    else
      echo "[setup] Recovering..."
      _reconnect
      _is_healthy || { echo "[setup] Recovery failed"; return 1; }
    fi
  else
    echo "[setup] Connecting..."
    agent-flutter connect 2>&1 || { _reconnect; }
    _is_healthy || { echo "[setup] Not healthy after connect"; return 1; }
  fi

  # Navigate to home tab to ensure consistent start state
  _go_home
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

af_snapshot_count() {
  af snapshot --json 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))"
}

af_snapshot_interactive_count() {
  af snapshot -i --json 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))"
}

af_count_type() {
  local widget_type="$1"
  af snapshot --json 2>/dev/null | python3 -c "
import sys, json
elems = json.load(sys.stdin)
print(len([e for e in elems if e.get('type') == '$widget_type']))
"
}

af_find_type() {
  local widget_type="$1"
  local index="${2:-0}"
  af snapshot --json 2>/dev/null | python3 -c "
import sys, json
matches = [e for e in json.load(sys.stdin) if e.get('type') == '$widget_type']
if len(matches) > $index: print(matches[$index]['ref'])
else: sys.exit(1)
"
}

# Screenshot (skipped in fast mode)
af_screenshot() {
  if [ "${E2E_FAST:-}" = "1" ]; then return 0; fi
  local name="$1"
  local path="$SCREENSHOT_DIR/${FLOW_NAME}-${STEP_NUM}-${name}.png"
  af screenshot "$path" 2>&1
  echo "  Screenshot: $path"
}

# --- Navigation helpers ---

af_press_wait() {
  af press "@$1" 2>&1
  af_wait
}

af_find_press() {
  local widget_type="$1"
  local index="${2:-}"
  if [ -n "$index" ]; then
    af find type "$widget_type" --index "$index" press 2>&1
  else
    af find type "$widget_type" press 2>&1
  fi
  af_wait
}
