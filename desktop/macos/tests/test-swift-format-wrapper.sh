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
  if echo "$haystack" | grep -qF -- "$needle"; then
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
# --- lint passes config file ---
assert_contains "$WRAPPER_TEXT" '--configuration "$CONFIG_FILE"' "lint uses pinned config file"

# --- config-path subcommand ---
CONFIG_PATH="$("$WRAPPER" config-path)"
assert_contains "$CONFIG_PATH" ".swift-format" "config-path returns config file"
[ -f "$CONFIG_PATH" ] && ok "config file exists on disk" || nok "config file not found"

# --- config is valid JSON with expected settings ---
python3 -c "
import json, sys
with open('$CONFIG_PATH') as f:
    cfg = json.load(f)
assert cfg.get('lineLength') == 120, f\"lineLength is {cfg.get('lineLength')}, expected 120\"
indent = cfg.get('indentation', {})
assert indent.get('spaces') == 2, f\"indentation.spaces is {indent.get('spaces')}, expected 2\"
assert cfg.get('tabWidth') == 2, f\"tabWidth is {cfg.get('tabWidth')}, expected 2\"
print('config: lineLength=120 indentation=2 tabWidth=2')
" && ok "config has correct lineLength, indentation, tabWidth" || nok "config validation failed"

# --- scope subcommand excludes Generated/ ---
SCOPE="$("$WRAPPER" scope)"
SCOPE_COUNT="$(echo "$SCOPE" | wc -l | tr -d ' ')"
if grep -q 'Generated/' <<< "$SCOPE"; then
  nok "scope includes Generated/ files (should be excluded)"
else
  ok "scope excludes Generated/ files"
fi
if grep -q '\.swift$' <<< "$SCOPE"; then
  ok "scope contains .swift files"
else
  nok "scope has no .swift files"
fi

# --- scope includes Tests/ directory ---
if grep -q 'Tests/' <<< "$SCOPE"; then
  ok "scope includes test files"
else
  nok "scope should include Tests/"
fi

echo "== ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ] || exit 1
