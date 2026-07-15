#!/usr/bin/env bash
# Unit tests for the pinned swift-format bootstrap wrapper (#9843 Ticket 02).
# Verifies pinned provenance constants, subcommand dispatch, and fail-closed
# behavior without requiring a full source build.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WRAPPER="$MACOS_DIR/scripts/swift-format-wrapper.sh"

PASS=0
FAIL=0

ok() { echo "  ok: $1"; PASS=$((PASS + 1)); }
nok() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

assert_contains() {
  local haystack="$1" needle="$2" label="$3"
  if echo "$haystack" | grep -qF "$needle"; then
    ok "$label"
  else
    nok "$label (expected '$needle' in output)"
  fi
}

echo "== swift-format-wrapper.sh unit tests"

# --- existence ---
[ -x "$WRAPPER" ] && ok "wrapper is executable" || nok "wrapper not executable"

# --- pinned constants ---
WRAPPER_TEXT="$(cat "$WRAPPER")"
assert_contains "$WRAPPER_TEXT" 'SWIFT_FORMAT_VERSION="602.0.0"' "version pinned to 602.0.0"
assert_contains "$WRAPPER_TEXT" 'SWIFT_FORMAT_COMMIT="62eaad2822b865407b8cde56c36386c00800f7ec"' "commit pinned to 62eaad2"
assert_contains "$WRAPPER_TEXT" 'swiftlang/swift-format.git' "uses swiftlang org repo"

# --- digest subcommand (no build required) ---
DIGEST="$("$WRAPPER" digest)"
assert_contains "$DIGEST" "62eaad2822b865407b8cde56c36386c00800f7ec" "digest prints pinned commit"

# --- binary-path subcommand (no build required) ---
BIN_PATH="$("$WRAPPER" binary-path)"
assert_contains "$BIN_PATH" "602.0.0" "binary-path includes version"
assert_contains "$BIN_PATH" "62eaad2822b8" "binary-path includes commit prefix"

# --- unknown subcommand fails closed ---
if ! "$WRAPPER" nonsense 2>/dev/null; then
  ok "unknown subcommand fails closed"
else
  nok "unknown subcommand should fail"
fi

# --- missing subcommand fails closed ---
if ! "$WRAPPER" 2>/dev/null; then
  ok "missing subcommand fails closed"
else
  nok "missing subcommand should fail"
fi

# --- lint subcommand includes --strict ---
assert_contains "$WRAPPER_TEXT" 'lint --strict' "lint uses --strict by default"

echo "== ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ] || exit 1
