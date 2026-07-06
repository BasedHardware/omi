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

# iOS IPA with a raw provider-shaped secret but no env var name
mkdir -p "$WORK/ios-shaped/Payload/Runner.app"
printf 'Authorization: Bearer sk-fake-not-real-release-guard-sentinel' \
  > "$WORK/ios-shaped/Payload/Runner.app/config.txt"
make_zip "$WORK/ios-shaped" "$WORK/shaped-secret.ipa"

# iOS IPA with xcframework variant
mkdir -p "$WORK/ios-xcfw/Payload/Runner.app/Frameworks/BoringSSL.xcframework/ios-arm64/BoringSSL.framework"
printf 'CLIENT_EARLY_TRAFFIC_SECRET\nEXPORTER_SECRET' \
  > "$WORK/ios-xcfw/Payload/Runner.app/Frameworks/BoringSSL.xcframework/ios-arm64/BoringSSL.framework/BoringSSL"
make_zip "$WORK/ios-xcfw" "$WORK/xcframework.ipa"

# Android AAB
mkdir -p "$WORK/android/build/app/outputs/bundle/prodRelease"
mkdir -p "$WORK/aab-content/base"
printf 'android app bundle content YOUR_API_KEY' > "$WORK/aab-content/base/manifest"
make_zip "$WORK/aab-content" "$WORK/android/build/app/outputs/bundle/prodRelease/app-prod-release.aab"

# Android AAB with an intentionally public SDK key value from CI env.
mkdir -p "$WORK/android-public-token"
mkdir -p "$WORK/aab-public-token/base"
printf 'BuildConfig INTERCOM_ANDROID_API_KEY public-intercom-android-token' > "$WORK/aab-public-token/base/classes.dex"
make_zip "$WORK/aab-public-token" "$WORK/android-public-token/app-prod-release.aab"

# Archive containing benign opaque resources that are not zip/tar payloads.
mkdir -p "$WORK/opaque/Payload/Runner.app"
printf 'asar payload bytes' > "$WORK/opaque/Payload/Runner.app/app.asar"
printf 'plain compressed data' > "$WORK/opaque/Payload/Runner.app/cache.gz"
printf '<plist><dict><key>API_KEY</key><string>AIzaFakePublicFirebaseKeyForReleaseGuard</string></dict></plist>' \
  > "$WORK/opaque/Payload/Runner.app/GoogleService-Info.plist"
make_zip "$WORK/opaque" "$WORK/opaque-resources.ipa"

# Empty build dir for nullglob test
mkdir -p "$WORK/android-empty/build"

# --- Tests ---

echo "=== Codemagic iOS workflow (line 186: build/ios/ipa/*.ipa) ==="
run_expect_pass "ios-framework-tokens-pass" \
  python3 "$SCANNER" "$WORK/framework.ipa"

echo ""
echo "=== Codemagic Android workflow (release AAB glob) ==="
run_expect_pass "android-aab-with-nullglob" \
  bash -c "cd '$WORK/android' && AAB_ARTIFACTS=\$(find build -path '*/outputs/*.aab' -print) && python3 '$SCANNER' \$AAB_ARTIFACTS"

echo ""
echo "=== Android public SDK token env value is allowed ==="
run_expect_pass "android-public-sdk-token-pass" \
  env INTERCOM_ANDROID_API_KEY=public-intercom-android-token python3 "$SCANNER" "$WORK/android-public-token/app-prod-release.aab"

echo ""
echo "=== Android no AAB built (warn and pass) ==="
run_expect_pass "android-empty-glob-warn-pass" \
  bash -c "cd '$WORK/android-empty' && AAB_ARTIFACTS=\$(find build -path '*/outputs/*.aab' -print) && python3 '$SCANNER' \$AAB_ARTIFACTS"

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
echo "=== Security: raw provider-shaped secret still caught ==="
run_expect_fail "provider-shaped-secret-caught" "OpenAI-shaped secret" \
  python3 "$SCANNER" "$WORK/shaped-secret.ipa"

echo ""
echo "=== Security: private key in text file outside framework still caught ==="
mkdir -p "$WORK/pk-text/Payload/Runner.app"
printf -- '-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----' \
  > "$WORK/pk-text/Payload/Runner.app/leaked.txt"
make_zip "$WORK/pk-text" "$WORK/privkey-text.ipa"
run_expect_fail "private-key-in-text-caught" "private key material" \
  python3 "$SCANNER" "$WORK/privkey-text.ipa"

echo ""
echo "=== Security: private key in binary outside framework skipped ==="
mkdir -p "$WORK/pk-bin/Payload/Runner.app"
printf -- '-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----' \
  > "$WORK/pk-bin/Payload/Runner.app/Runner"
make_zip "$WORK/pk-bin" "$WORK/privkey-bin.ipa"
run_expect_pass "private-key-in-binary-skipped" \
  python3 "$SCANNER" "$WORK/privkey-bin.ipa"

echo ""
echo "=== Security: exact denied name in text file outside framework caught ==="
mkdir -p "$WORK/exact-text/Payload/Runner.app"
printf 'OPENAI_API_KEY' > "$WORK/exact-text/Payload/Runner.app/config.json"
make_zip "$WORK/exact-text" "$WORK/exact-text.ipa"
run_expect_fail "exact-denied-in-text-caught" "OPENAI_API_KEY" \
  python3 "$SCANNER" "$WORK/exact-text.ipa"

echo ""
echo "=== Security: server secret in Info.plist caught ==="
mkdir -p "$WORK/plist-leak/Payload/Runner.app"
cat > "$WORK/plist-leak/Payload/Runner.app/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>GOOGLE_CLIENT_SECRET</key><string>not-a-real-secret</string>
</dict></plist>
EOF
make_zip "$WORK/plist-leak" "$WORK/plist-leak.ipa"
run_expect_fail "secret-in-info-plist-caught" "GOOGLE_CLIENT_SECRET" \
  python3 "$SCANNER" "$WORK/plist-leak.ipa"

echo ""
echo "=== Realistic Info.plist metadata passes ==="
mkdir -p "$WORK/plist-ok/Payload/Runner.app"
cat > "$WORK/plist-ok/Payload/Runner.app/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleURLTypes</key><array><dict>
    <key>CFBundleURLSchemes</key><array><string>$(GOOGLE_REVERSE_CLIENT_ID)</string></array>
  </dict></array>
  <key>UIBackgroundModes</key><array><string>audio</string><string>voip</string></array>
</dict></plist>
EOF
make_zip "$WORK/plist-ok" "$WORK/plist-ok.ipa"
run_expect_pass "realistic-info-plist-pass" \
  python3 "$SCANNER" "$WORK/plist-ok.ipa"

echo ""
echo "=== Compiled binaries with denied-looking symbols are skipped ==="
mkdir -p "$WORK/bin-ok/Payload/Runner.app/BatteryWidget.appex"
printf 'CLIENT_EARLY_TRAFFIC_SECRET\nPRIVATE_KEY_ENCODE_ERROR\nSERVER_HANDSHAKE_TRAFFIC_SECRET' \
  > "$WORK/bin-ok/Payload/Runner.app/Runner"
printf 'CREDENTIAL_MISMATCH\nAPI_KEY\nPROJECT_TOKEN' \
  > "$WORK/bin-ok/Payload/Runner.app/BatteryWidget.appex/BatteryWidget"
make_zip "$WORK/bin-ok" "$WORK/binary-ok.ipa"
run_expect_pass "compiled-binary-symbols-skipped" \
  python3 "$SCANNER" "$WORK/binary-ok.ipa"

echo ""
echo "=== Security: CI secret values inside framework still caught ==="
mkdir -p "$WORK/ci-fw/Payload/Runner.app/Frameworks/Leaked.framework"
printf 'not-a-real-secret-value-test-8742' \
  > "$WORK/ci-fw/Payload/Runner.app/Frameworks/Leaked.framework/Leaked"
make_zip "$WORK/ci-fw" "$WORK/ci-fw.ipa"
ENCRYPTION_SECRET=not-a-real-secret-value-test-8742 \
  run_expect_fail "ci-value-in-framework-still-caught" "current CI value" \
  python3 "$SCANNER" "$WORK/ci-fw.ipa"

echo ""
echo "=== Opaque resources and public Google client keys pass ==="
run_expect_pass "opaque-resources-pass" \
  python3 "$SCANNER" "$WORK/opaque-resources.ipa"

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
