#!/usr/bin/env bash
# Test scan-public-artifact-secrets.py against real Codemagic workflow patterns.
# Run from repo root: bash scripts/test-scan-public-artifact-secrets.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCANNER="$SCRIPT_DIR/scan-public-artifact-secrets.py"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

PASS=0
FAIL=0

run_expect_pass() {
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "PASS $name"
    ((PASS++))
  else
    echo "FAIL $name (expected pass, got exit $?)"
    ((FAIL++))
  fi
}

run_expect_fail() {
  local name="$1"
  local pattern="$2"
  shift 2
  local out rc
  out=$("$@" 2>&1) && rc=0 || rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "FAIL $name (expected fail, got pass)"
    ((FAIL++))
  elif echo "$out" | grep -q "$pattern"; then
    echo "PASS $name"
    ((PASS++))
  else
    echo "FAIL $name (failed but pattern '$pattern' not found)"
    echo "  output: $out"
    ((FAIL++))
  fi
}

make_zip() {
  local src="$1" dst="$2"
  (cd "$src" && zip -qr "$dst" .)
}

# --- Build test artifacts ---

# iOS IPA with framework BoringSSL constants
mkdir -p "$WORK/ios-fw/Payload/Runner.app/Frameworks/TwilioVoice.framework"
mkdir -p "$WORK/ios-fw/Payload/Runner.app/Frameworks/Flutter.framework"
printf 'CLIENT_EARLY_TRAFFIC_SECRET\nPRIVATE_KEY_ENCODE_ERROR\nSERVER_HANDSHAKE_TRAFFIC_SECRET\nEXPORTER_SECRET' \
  > "$WORK/ios-fw/Payload/Runner.app/Frameworks/TwilioVoice.framework/TwilioVoice"
printf 'CLIENT_EARLY_TRAFFIC_SECRET\nHANDSHAKE_SECRET\nMASTER_SECRET' \
  > "$WORK/ios-fw/Payload/Runner.app/Frameworks/Flutter.framework/Flutter"
printf 'normal app binary' > "$WORK/ios-fw/Payload/Runner.app/Runner"
make_zip "$WORK/ios-fw" "$WORK/framework.ipa"

# iOS IPA with real secret leak outside framework
mkdir -p "$WORK/ios-leak/Payload/Runner.app/Frameworks/TwilioVoice.framework"
printf 'CLIENT_EARLY_TRAFFIC_SECRET' \
  > "$WORK/ios-leak/Payload/Runner.app/Frameworks/TwilioVoice.framework/TwilioVoice"
printf 'OPENAI_API_KEY=sk-test123' > "$WORK/ios-leak/Payload/Runner.app/leaked.env"
make_zip "$WORK/ios-leak" "$WORK/leaked.ipa"

# iOS IPA with private key inside framework
mkdir -p "$WORK/ios-pk/Payload/Runner.app/Frameworks/Bad.framework"
printf -- '-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----' \
  > "$WORK/ios-pk/Payload/Runner.app/Frameworks/Bad.framework/Bad"
make_zip "$WORK/ios-pk" "$WORK/privkey.ipa"

# iOS IPA with exact denied name inside framework
mkdir -p "$WORK/ios-exact/Payload/Runner.app/Frameworks/Leaked.framework"
printf 'OPENAI_API_KEY' \
  > "$WORK/ios-exact/Payload/Runner.app/Frameworks/Leaked.framework/Leaked"
make_zip "$WORK/ios-exact" "$WORK/exact-denied.ipa"

# iOS IPA with xcframework variant
mkdir -p "$WORK/ios-xcfw/Payload/Runner.app/Frameworks/BoringSSL.xcframework/ios-arm64/BoringSSL.framework"
printf 'CLIENT_EARLY_TRAFFIC_SECRET\nEXPORTER_SECRET' \
  > "$WORK/ios-xcfw/Payload/Runner.app/Frameworks/BoringSSL.xcframework/ios-arm64/BoringSSL.framework/BoringSSL"
make_zip "$WORK/ios-xcfw" "$WORK/xcframework.ipa"

# Android AAB
mkdir -p "$WORK/android/build/app/outputs/bundle/prodRelease"
mkdir -p "$WORK/aab-content/base"
printf 'android app bundle content' > "$WORK/aab-content/base/manifest"
make_zip "$WORK/aab-content" "$WORK/android/build/app/outputs/bundle/prodRelease/app-prod-release.aab"

# Empty build dir for nullglob test
mkdir -p "$WORK/android-empty/build"

# --- Tests ---

echo "=== Codemagic iOS workflow (line 186: build/ios/ipa/*.ipa) ==="
run_expect_pass "ios-framework-tokens-pass" \
  python3 "$SCANNER" "$WORK/framework.ipa"

echo ""
echo "=== Codemagic Android workflow (lines 430-431: shopt -s globstar nullglob + glob) ==="
run_expect_pass "android-aab-with-nullglob" \
  bash -c "cd '$WORK/android' && shopt -s globstar nullglob && python3 '$SCANNER' build/**/outputs/**/*.aab"

echo ""
echo "=== Android nullglob + no AAB built (warn and pass) ==="
run_expect_pass "android-empty-glob-warn-pass" \
  bash -c "cd '$WORK/android-empty' && shopt -s globstar nullglob && python3 '$SCANNER' build/**/outputs/**/*.aab"

echo ""
echo "=== Security: real secret outside framework still caught ==="
run_expect_fail "secret-outside-framework-caught" "OPENAI_API_KEY" \
  python3 "$SCANNER" "$WORK/leaked.ipa"

echo ""
echo "=== Security: private key markers inside framework skipped ==="
run_expect_pass "private-key-in-framework-skipped" \
  python3 "$SCANNER" "$WORK/privkey.ipa"

echo ""
echo "=== Security: exact denied name inside framework skipped ==="
run_expect_pass "exact-denied-in-framework-skipped" \
  python3 "$SCANNER" "$WORK/exact-denied.ipa"

echo ""
echo "=== Security: private key markers OUTSIDE framework still caught ==="
mkdir -p "$WORK/pk-outside/Payload/Runner.app"
printf -- '-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----' \
  > "$WORK/pk-outside/Payload/Runner.app/leaked"
make_zip "$WORK/pk-outside" "$WORK/privkey-outside.ipa"
run_expect_fail "private-key-outside-framework-caught" "private key material" \
  python3 "$SCANNER" "$WORK/privkey-outside.ipa"

echo ""
echo "=== Security: exact denied name OUTSIDE framework still caught ==="
mkdir -p "$WORK/exact-outside/Payload/Runner.app"
printf 'OPENAI_API_KEY' > "$WORK/exact-outside/Payload/Runner.app/config"
make_zip "$WORK/exact-outside" "$WORK/exact-outside.ipa"
run_expect_fail "exact-denied-outside-framework-caught" "OPENAI_API_KEY" \
  python3 "$SCANNER" "$WORK/exact-outside.ipa"

echo ""
echo "=== Security: CI secret values inside framework still caught ==="
mkdir -p "$WORK/ci-fw/Payload/Runner.app/Frameworks/Leaked.framework"
printf 'not-a-real-secret-value-test-8741' \
  > "$WORK/ci-fw/Payload/Runner.app/Frameworks/Leaked.framework/Leaked"
make_zip "$WORK/ci-fw" "$WORK/ci-fw.ipa"
ENCRYPTION_SECRET=not-a-real-secret-value-test-8741 \
  run_expect_fail "ci-value-in-framework-still-caught" "current CI value" \
  python3 "$SCANNER" "$WORK/ci-fw.ipa"

echo ""
echo "=== xcframework tokens pass (nested .xcframework/.framework) ==="
run_expect_pass "xcframework-tokens-pass" \
  python3 "$SCANNER" "$WORK/xcframework.ipa"

echo ""
echo "=== No arguments at all (warn and pass) ==="
run_expect_pass "no-args-warn-pass" \
  python3 "$SCANNER"

echo ""
echo "================================"
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
