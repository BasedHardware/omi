#!/usr/bin/env bash
# Focused, self-driving harness for desktop agent / realtime voice control-plane changes.
#
# Usage:
#   cd desktop/macos && ./scripts/agent-logic-harness.sh
#   ./scripts/agent-logic-harness.sh --swift-only
#   ./scripts/agent-logic-harness.sh --node-only
#   ./scripts/agent-logic-harness.sh --skip-install
#   ./scripts/agent-logic-harness.sh --verbose
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DESKTOP_DIR/../.." && pwd)"

RUN_SWIFT=1
RUN_NODE=1
SKIP_INSTALL=0
VERBOSE=0
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$DESKTOP_DIR/.harness/agent-logic/$RUN_ID"

usage() {
  cat <<'USAGE'
Focused harness for Omi desktop agent / voice logic.

Runs:
  1. Swift focused tests:
     AgentPillLifecycleTests, PushToTalkStateMachineTests, RealtimeHubSpawnAgentTests
  2. Agent runtime focused tests:
     codemagic-pi-mono-extension-ci, runtime-adapter, pi-mono-adapter
  3. pi-mono-extension package tests:
     npm ci if needed, then node --experimental-strip-types --test index.test.ts

Options:
  --swift-only    Run only Swift focused tests
  --node-only     Run only Node/package focused tests
  --skip-install  Do not run npm ci for pi-mono-extension if deps are missing
  --verbose       Stream command output instead of saving it quietly
  --help          Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --swift-only)
      RUN_SWIFT=1
      RUN_NODE=0
      ;;
    --node-only)
      RUN_SWIFT=0
      RUN_NODE=1
      ;;
    --skip-install)
      SKIP_INSTALL=1
      ;;
    --verbose)
      VERBOSE=1
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ "$RUN_SWIFT" -eq 0 && "$RUN_NODE" -eq 0 ]]; then
  echo "Nothing selected." >&2
  exit 2
fi

declare -a STEP_NAMES=()
declare -a STEP_SECONDS=()
declare -a STEP_LOGS=()

now_seconds() {
  python3 - <<'PY'
import time
print(f"{time.monotonic():.6f}")
PY
}

elapsed_seconds() {
  local start="$1"
  python3 - "$start" <<'PY'
import sys, time
start = float(sys.argv[1])
print(f"{time.monotonic() - start:.2f}")
PY
}

run_step() {
  local name="$1"
  shift
  echo
  echo "=== $name ==="
  local start
  local log_path="$RUN_DIR/$(printf '%02d' "$((${#STEP_NAMES[@]} + 1))")-$(echo "$name" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9._-').log"
  start="$(now_seconds)"
  if [[ "$VERBOSE" -eq 1 ]]; then
    "$@" 2>&1 | tee "$log_path"
  elif ! "$@" >"$log_path" 2>&1; then
    local status=$?
    echo "--- $name failed; log: $log_path" >&2
    cat "$log_path" >&2
    exit "$status"
  fi
  local elapsed
  elapsed="$(elapsed_seconds "$start")"
  STEP_NAMES+=("$name")
  STEP_SECONDS+=("$elapsed")
  STEP_LOGS+=("$log_path")
  echo "--- $name passed in ${elapsed}s (log: $log_path)"
}

run_swift_focus() {
  (
    cd "$DESKTOP_DIR"
    xcrun swift test --package-path Desktop \
      --filter 'AgentPillLifecycleTests|PushToTalkStateMachineTests|RealtimeHubSpawnAgentTests'
  )
}

run_agent_runtime_focus() {
  (
    cd "$DESKTOP_DIR/agent"
    npm test -- --run \
      tests/codemagic-pi-mono-extension-ci.test.ts \
      tests/runtime-adapter.test.ts \
      tests/pi-mono-adapter.test.ts
  )
}

ensure_pi_mono_extension_deps() {
  if [[ -d "$DESKTOP_DIR/pi-mono-extension/node_modules" ]]; then
    return
  fi
  if [[ "$SKIP_INSTALL" -eq 1 ]]; then
    echo "pi-mono-extension/node_modules missing and --skip-install was set" >&2
    return 1
  fi
  (
    cd "$DESKTOP_DIR/pi-mono-extension"
    npm ci --no-fund --no-audit
  )
}

run_pi_mono_extension_exact() {
  ensure_pi_mono_extension_deps
  (
    cd "$DESKTOP_DIR/pi-mono-extension"
    node --experimental-strip-types --test index.test.ts
  )
}

total_start="$(now_seconds)"

echo "Omi desktop agent logic harness"
echo "repo: $REPO_ROOT"
echo "desktop: $DESKTOP_DIR"
echo "git: $(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
mkdir -p "$RUN_DIR"
echo "logs: $RUN_DIR"

if [[ "$RUN_SWIFT" -eq 1 ]]; then
  run_step "swift focused lifecycle/state tests" run_swift_focus
fi

if [[ "$RUN_NODE" -eq 1 ]]; then
  run_step "agent runtime focused tests" run_agent_runtime_focus
  run_step "pi-mono-extension exact package tests" run_pi_mono_extension_exact
fi

total_elapsed="$(elapsed_seconds "$total_start")"

echo
echo "=== Timing Summary ==="
for i in "${!STEP_NAMES[@]}"; do
  printf '%7ss  %s  (%s)\n' "${STEP_SECONDS[$i]}" "${STEP_NAMES[$i]}" "${STEP_LOGS[$i]}"
done
printf '%7ss  TOTAL\n' "$total_elapsed"

echo
echo "Harness passed."
