#!/usr/bin/env bash
#
# Behavioral tests for detect_apple_team_id() in app/setup.sh.
#
# These drive the real function through two seams — $HOME (where it looks for
# provisioning profiles) and stdin (whether a human is attached) — rather than
# asserting on the source text.
#
# Regression covered: with no detectable team and no TTY, the function used to
# block forever on `read`, hanging setup.sh in CI and nested automation. It must
# fail fast with a non-zero status instead.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_SH="${SCRIPT_DIR}/../../setup.sh"

if [[ ! -f "$SETUP_SH" ]]; then
  echo "FAIL: cannot find setup.sh at $SETUP_SH" >&2
  exit 1
fi

failures=0

pass() { echo "  ok   - $1"; }
fail() { echo "  FAIL - $1" >&2; failures=$((failures + 1)); }

# Extract the helper functions under test into a standalone harness, so we don't
# execute setup.sh's top-level body (which prints banners and expects args).
HARNESS="$(mktemp -t omi_detect_team_XXXXXX)"
trap 'rm -f "$HARNESS"' EXIT

extract_function() {
  # Prints from "function <name>()" through the first line that is exactly "}".
  awk -v fn="function $1()" '
    index($0, fn) == 1 { capture = 1 }
    capture { print }
    capture && $0 == "}" { exit }
  ' "$SETUP_SH"
}

{
  echo "set -uo pipefail"
  extract_function generate_device_suffix
  extract_function detect_apple_team_id
} > "$HARNESS"

if ! bash -n "$HARNESS"; then
  echo "FAIL: extracted harness is not valid bash" >&2
  exit 1
fi

# Run a command with a deadline, without depending on GNU `timeout` being
# present. Exits 124 if the deadline is hit, mirroring timeout(1).
run_with_deadline() {
  local deadline="$1"; shift
  local rc=0
  ( "$@" ) & local pid=$!
  ( sleep "$deadline"; kill -9 "$pid" 2>/dev/null ) & local killer=$!
  wait "$pid" 2>/dev/null || rc=$?
  kill "$killer" 2>/dev/null
  wait "$killer" 2>/dev/null || true
  # 137 == SIGKILL from the deadline watchdog
  if [[ "$rc" -eq 137 ]]; then return 124; fi
  return "$rc"
}

echo "detect_apple_team_id:"

# ---------------------------------------------------------------------------
# 1. An explicit APPLE_DEVELOPMENT_TEAM override wins, with no filesystem or
#    keychain access at all.
# ---------------------------------------------------------------------------
got="$(APPLE_DEVELOPMENT_TEAM=ABCDE12345 bash -c "source '$HARNESS'; detect_apple_team_id" 2>/dev/null)"
if [[ "$got" == "ABCDE12345" ]]; then
  pass "honours APPLE_DEVELOPMENT_TEAM override"
else
  fail "expected override 'ABCDE12345', got '${got}'"
fi

# ---------------------------------------------------------------------------
# 2. No override, no discoverable profiles, no TTY -> must fail fast rather than
#    block on read. An empty $HOME guarantees the profile scan finds nothing.
# ---------------------------------------------------------------------------
empty_home="$(mktemp -d -t omi_empty_home_XXXXXX)"
rc=0
run_with_deadline 20 env -u APPLE_DEVELOPMENT_TEAM HOME="$empty_home" \
  bash -c "source '$HARNESS'; detect_apple_team_id < /dev/null" >/dev/null 2>&1 || rc=$?
rm -rf "$empty_home"

case "$rc" in
  124) fail "hung waiting for input with no TTY (the regression)" ;;
  0)   fail "reported success despite having no team to detect" ;;
  *)   pass "fails fast (rc=$rc) instead of blocking on read without a TTY" ;;
esac

echo
if [[ "$failures" -gt 0 ]]; then
  echo "$failures shell test(s) failed" >&2
  exit 1
fi
echo "all detect_apple_team_id shell tests passed"
