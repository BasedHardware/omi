#!/usr/bin/env bash
set -euo pipefail

# Regression test for the BUNDLE_ID patch in generate_ios_custom_config(): the
# prebuilt/placeholder GoogleService-Info.plist always carries a fixed, unsuffixed
# BUNDLE_ID, but Dev builds get a per-hostname-suffixed APP_BUNDLE_IDENTIFIER. Left
# unpatched, that mismatch crashes Firebase.initializeApp() on-device with a generic
# "invalid GOOGLE_APP_ID" error that names the wrong field — measured directly on
# iOS 27 hardware. See app/test/unit/firebase_local_options_test.dart for the sibling
# regression test on the placeholder values' own format.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

source setup.sh

# Override machine/environment-dependent helpers so this test is hermetic: the real
# generate_device_suffix reads the local hostname, and detect_apple_team_id inspects
# this machine's signing identities (and prompts interactively as a last resort).
generate_device_suffix() { echo "testhost"; }
detect_apple_team_id() { echo "TESTTEAM01"; }

fixture_dir="$(mktemp -d "${TMPDIR:-/tmp}/omi-ios-custom-config.XXXXXX")"
trap 'rm -rf "$fixture_dir"' EXIT

mkdir -p "$fixture_dir/ios/Config/Dev" "$fixture_dir/ios/Flutter" "$fixture_dir/scripts"
cp scripts/generate_ios_custom_config.sh "$fixture_dir/scripts/generate_ios_custom_config.sh"
cp setup/prebuilt/GoogleService-Info-Local.plist "$fixture_dir/ios/Config/Dev/GoogleService-Info.plist"
cp setup/prebuilt/GoogleService-Info-Local.plist "$fixture_dir/ios/Runner/GoogleService-Info.plist" 2>/dev/null \
  || { mkdir -p "$fixture_dir/ios/Runner"; cp setup/prebuilt/GoogleService-Info-Local.plist "$fixture_dir/ios/Runner/GoogleService-Info.plist"; }

before_bundle_id="$(/usr/libexec/PlistBuddy -c 'Print :BUNDLE_ID' "$fixture_dir/ios/Config/Dev/GoogleService-Info.plist")"

(
  cd "$fixture_dir"
  generate_ios_custom_config Dev omi-dev
)

config_bundle_id="$(/usr/libexec/PlistBuddy -c 'Print :BUNDLE_ID' "$fixture_dir/ios/Config/Dev/GoogleService-Info.plist")"
runner_bundle_id="$(/usr/libexec/PlistBuddy -c 'Print :BUNDLE_ID' "$fixture_dir/ios/Runner/GoogleService-Info.plist")"
xcconfig_bundle_id="$(grep '^APP_BUNDLE_IDENTIFIER=' "$fixture_dir/ios/Flutter/Custom.xcconfig" | cut -d= -f2)"

[[ "$config_bundle_id" == "$xcconfig_bundle_id" ]]
[[ "$runner_bundle_id" == "$xcconfig_bundle_id" ]]
[[ "$config_bundle_id" != "$before_bundle_id" ]]
[[ "$config_bundle_id" == "com.friend-app-with-wearable.ios12-testhost" ]]

echo "generate_ios_custom_config patches GoogleService-Info.plist BUNDLE_ID to match the suffixed bundle id"
