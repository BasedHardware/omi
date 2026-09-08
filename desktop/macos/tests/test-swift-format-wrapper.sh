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
assert_contains "$WRAPPER_TEXT" '--depth 1 --branch "$SWIFT_FORMAT_VERSION"' "uses a depth-one pinned tag clone"

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

# --- lint subcommand includes --strict and config, but NOT --in-place ---
assert_contains "$WRAPPER_TEXT" '--configuration "$CONFIG_FILE"' "lint uses pinned config file"

# --- no-write in lint mode: extract the lint case body and verify no --in-place/-i ---
LINT_BODY="$(sed -n '/^  lint)/,/^    ;;/p' "$WRAPPER")"
if echo "$LINT_BODY" | grep -qE '\-\-in-place| -i '; then
  nok "lint case contains --in-place/-i (must be read-only)"
else
  ok "lint mode does not write files (no --in-place/-i in lint case)"
fi

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
# --- bootstrap serialization ---
# Two concurrent bootstraps used to delete each other's build tree: `bootstrap`
# opens with `rm -rf "$BUILD_DIR"`, so the second invocation removed the first
# one's object files mid-compile. Observed live across two worktrees sharing the
# one cache, which left no binary behind and broke every commit hook until the
# cache was rebuilt by hand.
assert_contains "$WRAPPER_TEXT" 'mkdir "$LOCK_DIR"' "lock uses mkdir (atomic, no external binary)"

# Assert against the bootstrap body, not the whole file — the function
# *definition* matches either way, so a whole-file grep would still pass with
# the call deleted. `|| true` keeps a missing match reporting as a failed
# assertion instead of killing the suite under `set -e`.
BOOTSTRAP_BODY="$(sed -n '/^bootstrap() {/,/^}/p' "$WRAPPER")"
if echo "$BOOTSTRAP_BODY" | grep -q 'acquire_bootstrap_lock'; then
  ok "bootstrap calls acquire_bootstrap_lock"
else
  nok "bootstrap must call acquire_bootstrap_lock"
fi

# The lock must be taken before the destructive `rm -rf`, not after it.
LOCK_LINE="$(echo "$BOOTSTRAP_BODY" | grep -n 'acquire_bootstrap_lock' | head -1 | cut -d: -f1 || true)"
RM_LINE="$(echo "$BOOTSTRAP_BODY" | grep -n 'rm -rf "$BUILD_DIR"' | head -1 | cut -d: -f1 || true)"
if [ -n "$LOCK_LINE" ] && [ -n "$RM_LINE" ] && [ "$LOCK_LINE" -lt "$RM_LINE" ]; then
  ok "lock is acquired before the destructive rm -rf"
else
  nok "lock must be acquired before rm -rf (lock line '${LOCK_LINE:-none}', rm line '${RM_LINE:-none}')"
fi

# A waiter must re-check the cache under the lock, or every queued process
# still pays a full rebuild after the holder already produced the binary.
if echo "$BOOTSTRAP_BODY" | sed -n "/acquire_bootstrap_lock/,\$p" | grep -q 'cached_binary_is_current' 2>/dev/null; then
  ok "re-checks the cache after acquiring the lock"
else
  nok "must re-check the cache after acquiring the lock"
fi

LOCK_PATH="$("$WRAPPER" lock-path)"
assert_contains "$LOCK_PATH" ".lock" "lock-path reports the lock directory"

# Behavioral: a live holder makes a second bootstrap wait rather than build.
# Pointed at an empty cache so the fast path cannot short-circuit, and bounded
# by a 2s timeout so the assertion never reaches the ~15-minute build.
LOCK_TEST_CACHE="$(mktemp -d)"
HELD_LOCK="$(SWIFT_FORMAT_CACHE_DIR="$LOCK_TEST_CACHE" "$WRAPPER" lock-path)"
sleep 120 &
HOLDER_PID=$!
mkdir -p "$HELD_LOCK"
echo "$HOLDER_PID" > "$HELD_LOCK/owner"

set +e
CONTENDED="$(SWIFT_FORMAT_CACHE_DIR="$LOCK_TEST_CACHE" SWIFT_FORMAT_LOCK_TIMEOUT=2 "$WRAPPER" bootstrap 2>&1)"
CONTENDED_STATUS=$?
set -e
if [ "$CONTENDED_STATUS" -ne 0 ]; then
  ok "a held lock blocks a second bootstrap instead of racing it"
else
  nok "second bootstrap should not proceed while the lock is held"
fi
assert_contains "$CONTENDED" "waiting" "waiting bootstrap says who holds the lock"
if [ -f "$HELD_LOCK/owner" ] && [ "$(cat "$HELD_LOCK/owner")" = "$HOLDER_PID" ]; then
  ok "a waiter leaves the live holder's lock intact"
else
  nok "waiter must not steal or clear a live holder's lock"
fi
kill "$HOLDER_PID" 2>/dev/null || true
wait "$HOLDER_PID" 2>/dev/null || true

# Behavioral: a lock whose holder died is reclaimed rather than waited out
# forever. Reuses the just-killed pid, which is guaranteed dead. The bootstrap
# would go on to a real build, so it is killed as soon as it reports the
# reclaim — the assertion is on the reclaim, not on the build.
echo "$HOLDER_PID" > "$HELD_LOCK/owner"
RECLAIM_LOG="$LOCK_TEST_CACHE/reclaim.log"
SWIFT_FORMAT_CACHE_DIR="$LOCK_TEST_CACHE" SWIFT_FORMAT_LOCK_TIMEOUT=30 \
  "$WRAPPER" bootstrap >"$RECLAIM_LOG" 2>&1 &
BOOT_PID=$!
for _ in $(seq 1 20); do
  grep -q "reclaiming bootstrap lock" "$RECLAIM_LOG" 2>/dev/null && break
  sleep 0.5
done
kill "$BOOT_PID" 2>/dev/null || true
wait "$BOOT_PID" 2>/dev/null || true
assert_contains "$(cat "$RECLAIM_LOG" 2>/dev/null || true)" \
  "reclaiming bootstrap lock from dead pid" "a dead holder's lock is reclaimed"
rm -rf "$LOCK_TEST_CACHE"

# --- enforcement fixtures (require bootstrapped binary; skip on non-macOS) ---
if command -v xcrun >/dev/null 2>&1 && [ -x "$("$WRAPPER" binary-path)" ]; then
  TMP_SWIFT="$(mktemp -d)/test.swift"
  echo 'struct Foo{let x:Int}' > "$TMP_SWIFT"

  # Malformed Swift fails lint
  if "$WRAPPER" lint "$TMP_SWIFT" >/dev/null 2>&1; then
    nok "lint should fail on malformed Swift"
  else
    ok "lint fails on malformed Swift"
  fi

  # Format corrects it
  "$WRAPPER" format -i "$TMP_SWIFT" >/dev/null 2>&1
  if grep -q '^struct Foo {' "$TMP_SWIFT"; then
    ok "format corrects spacing in struct declaration"
  else
    nok "format did not correct struct spacing"
  fi

  # Lint passes after format (idempotent)
  if "$WRAPPER" lint "$TMP_SWIFT" >/dev/null 2>&1; then
    ok "lint passes after format (clean)"
  else
    nok "lint should pass after format"
  fi

  rm -rf "$(dirname "$TMP_SWIFT")"
else
  echo "  skip: formatter enforcement fixtures (no bootstrapped binary)"
fi

echo "== ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ] || exit 1
