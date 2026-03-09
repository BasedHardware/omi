#!/usr/bin/env bash
# Run all E2E flows and report summary.
#
# Usage:
#   # Fast: let the script manage flutter run (most reliable)
#   app/e2e/run-all.sh
#
#   # Use existing flutter run (must be fresh, not idle)
#   AGENT_FLUTTER_LOG=/tmp/flutter-run.log app/e2e/run-all.sh
#
# Env vars:
#   E2E_FAST=1          Skip screenshots (default: 1)
#   E2E_WAIT=0.2        Wait between actions in seconds (default: 0.2)
#   E2E_SCREENSHOT_DIR  Screenshot output dir (default: /tmp/omi-e2e)
#   E2E_APP_DIR         Flutter app directory (default: app/)
#   AGENT_FLUTTER_LOG   Flutter run log file (auto-created if not set)
#   AGENT_FLUTTER_DEVICE Device ID (default: emulator-5554)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
APP_DIR="${E2E_APP_DIR:-$REPO_DIR/app}"
DEVICE="${AGENT_FLUTTER_DEVICE:-emulator-5554}"

export E2E_FAST="${E2E_FAST:-1}"
export E2E_WAIT="${E2E_WAIT:-0.2}"

# Pre-flight checks
if ! command -v agent-flutter &>/dev/null; then
  echo "ERROR: agent-flutter not found. Install: npm install -g beastoin/agent-flutter"
  exit 1
fi

if ! adb devices 2>/dev/null | grep -q "$DEVICE"; then
  echo "ERROR: Device $DEVICE not found. Run: adb devices"
  exit 1
fi

# Start flutter run if no log file provided
FLUTTER_PID=""
if [ -z "${AGENT_FLUTTER_LOG:-}" ]; then
  echo "[boot] Starting flutter run..."
  export AGENT_FLUTTER_LOG="/tmp/omi-e2e-flutter.log"
  cd "$APP_DIR" && flutter run -d "$DEVICE" --flavor dev > "$AGENT_FLUTTER_LOG" 2>&1 &
  FLUTTER_PID=$!
  cd "$REPO_DIR"

  # Poll for VM Service (timeout 90s)
  echo "[boot] Waiting for VM Service..."
  for i in $(seq 1 90); do
    if grep -q "Dart VM Service" "$AGENT_FLUTTER_LOG" 2>/dev/null; then
      grep "Dart VM Service" "$AGENT_FLUTTER_LOG" | tail -1
      break
    fi
    if [ "$i" -eq 90 ]; then
      echo "ERROR: Flutter run timed out after 90s"
      kill -9 "$FLUTTER_PID" 2>/dev/null
      exit 1
    fi
    sleep 1
  done
fi

# Connect
echo "[boot] Connecting agent-flutter..."
agent-flutter disconnect 2>/dev/null || true
agent-flutter connect 2>&1 || { echo "ERROR: Could not connect"; exit 1; }

echo ""
echo "============================================"
echo "  Omi E2E Test Suite"
echo "============================================"
echo "  Mode: $([ "$E2E_FAST" = "1" ] && echo "fast" || echo "normal")"
echo "  Wait: ${E2E_WAIT}s"
echo ""

TOTAL_PASS=0
TOTAL_FAIL=0
RESULTS=""

run_flow() {
  local name="$1"
  local script="$2"
  echo ""
  echo "--------------------------------------------"
  echo "  $name"
  echo "--------------------------------------------"

  if bash "$SCRIPT_DIR/$script" 2>&1; then
    RESULTS="$RESULTS"$'\n'"  PASS  $name"
    TOTAL_PASS=$((TOTAL_PASS + 1))
  else
    RESULTS="$RESULTS"$'\n'"  FAIL  $name"
    TOTAL_FAIL=$((TOTAL_FAIL + 1))
  fi
}

START_TIME=$(date +%s)

run_flow "Flow 1: Home Navigation"   "flow1-home-navigation.sh"
run_flow "Flow 2: Settings Toggle"   "flow2-settings-toggle.sh"
run_flow "Flow 3: Tab Navigation"    "flow3-tab-navigation.sh"
run_flow "Flow 4: Language Change"   "flow4-language-change.sh"

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
echo "============================================"
echo "  RESULTS"
echo "============================================"
echo "$RESULTS"
echo ""
echo "  $((TOTAL_PASS + TOTAL_FAIL)) flows, $TOTAL_PASS passed, $TOTAL_FAIL failed"
echo "  Time: ${ELAPSED}s"
echo "============================================"

# Cleanup: kill flutter if we started it
if [ -n "$FLUTTER_PID" ]; then
  kill "$FLUTTER_PID" 2>/dev/null
fi

if [ "$TOTAL_FAIL" -gt 0 ]; then exit 1; fi
