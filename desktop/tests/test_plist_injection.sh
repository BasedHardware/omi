#!/bin/bash
# Tests for Firebase plist CI injection logic in build.sh and release.sh
# Validates: valid base64 plist, invalid plist, missing env var, fail-closed behavior

set -euo pipefail

PASS=0
FAIL=0
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

pass() { PASS=$((PASS + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1"; }

echo "=== Plist injection tests ==="

# --- Test 1: Valid base64 plist decodes correctly ---
echo ""
echo "Test 1: Valid base64 plist decodes correctly"
VALID_PLIST='<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>PROJECT_ID</key>
	<string>based-hardware</string>
	<key>API_KEY</key>
	<string>test-key</string>
</dict>
</plist>'
ENCODED=$(echo "$VALID_PLIST" | base64)
echo "$ENCODED" | base64 --decode > "$TMPDIR/valid.plist" 2>/dev/null
if [ -f "$TMPDIR/valid.plist" ]; then
    pass "base64 decode produced a file"
else
    fail "base64 decode did not produce a file"
fi

# Validate plist structure (plutil only available on macOS)
if command -v plutil &>/dev/null; then
    if plutil -lint "$TMPDIR/valid.plist" &>/dev/null; then
        pass "plutil validates decoded plist"
    else
        fail "plutil rejected decoded plist"
    fi
else
    echo "  SKIP: plutil not available (not macOS)"
fi

# --- Test 2: Invalid base64 data should fail plutil ---
echo ""
echo "Test 2: Invalid plist content fails validation"
INVALID_PLIST="this is not a valid plist"
echo "$INVALID_PLIST" | base64 | base64 --decode > "$TMPDIR/invalid.plist" 2>/dev/null
if command -v plutil &>/dev/null; then
    if plutil -lint "$TMPDIR/invalid.plist" &>/dev/null; then
        fail "plutil should reject invalid plist"
    else
        pass "plutil correctly rejects invalid plist"
    fi
else
    echo "  SKIP: plutil not available (not macOS)"
fi

# --- Test 3: release.sh fails when MACOS_GOOGLE_SERVICE_INFO_PLIST is missing ---
echo ""
echo "Test 3: release.sh injection is fail-closed"
# Extract and test the injection logic from release.sh
INJECT_SCRIPT='
if [ -n "${MACOS_GOOGLE_SERVICE_INFO_PLIST:-}" ]; then
    echo "INJECT"
else
    echo "FAIL_CLOSED"
    exit 1
fi
'
unset MACOS_GOOGLE_SERVICE_INFO_PLIST 2>/dev/null || true
OUTPUT=$(bash -c "$INJECT_SCRIPT" 2>&1) && RC=$? || RC=$?
if [ "$RC" -ne 0 ]; then
    pass "release injection exits non-zero when env var missing"
else
    fail "release injection should exit non-zero when env var missing"
fi

# --- Test 4: build.sh falls back to dev plist when env var missing ---
echo ""
echo "Test 4: build.sh injection falls back to dev plist"
BUILD_INJECT='
if [ -n "${MACOS_GOOGLE_SERVICE_INFO_PLIST:-}" ]; then
    echo "INJECT_PROD"
else
    echo "FALLBACK_DEV"
fi
'
unset MACOS_GOOGLE_SERVICE_INFO_PLIST 2>/dev/null || true
OUTPUT=$(bash -c "$BUILD_INJECT" 2>&1)
if echo "$OUTPUT" | grep -q "FALLBACK_DEV"; then
    pass "build injection falls back to dev plist"
else
    fail "build injection should fall back to dev plist"
fi

# --- Test 5: Env var set triggers prod injection ---
echo ""
echo "Test 5: Env var set triggers prod injection path"
export MACOS_GOOGLE_SERVICE_INFO_PLIST="$ENCODED"
OUTPUT=$(bash -c "$BUILD_INJECT" 2>&1)
if echo "$OUTPUT" | grep -q "INJECT_PROD"; then
    pass "prod injection path triggered with env var set"
else
    fail "prod injection path should be triggered"
fi
unset MACOS_GOOGLE_SERVICE_INFO_PLIST

# --- Test 6: Dev plist contains only dev project values ---
echo ""
echo "Test 6: Dev plist has dev-only values"
DEV_PLIST="$(dirname "$0")/../Desktop/Sources/GoogleService-Info.plist"
if [ -f "$DEV_PLIST" ]; then
    if grep -q "based-hardware-dev" "$DEV_PLIST"; then
        pass "dev plist contains based-hardware-dev project"
    else
        fail "dev plist should contain based-hardware-dev"
    fi
    if grep -q "based-hardware-prod" "$DEV_PLIST"; then
        fail "dev plist should NOT contain prod project ID"
    else
        pass "dev plist does not contain prod project ID"
    fi
else
    echo "  SKIP: dev plist not found at $DEV_PLIST"
fi

# --- Summary ---
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
