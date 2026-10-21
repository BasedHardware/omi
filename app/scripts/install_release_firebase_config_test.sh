#!/usr/bin/env bash
set -euo pipefail

# The release Firebase installer must place every file the release build reads, and each
# file must point at the right Firebase project and bundle/package identity.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
fixture_dir="$(mktemp -d "${TMPDIR:-/tmp}/omi-release-firebase.XXXXXX")"
trap 'rm -rf "$fixture_dir"' EXIT

bash "$ROOT_DIR/scripts/install_release_firebase_config.sh" "$fixture_dir" >/dev/null

fail() { echo "FAIL: $*" >&2; exit 1; }

for path in \
  lib/firebase_options_prod.dart lib/firebase_options_dev.dart \
  android/app/src/prod/google-services.json android/app/src/dev/google-services.json \
  ios/Config/Prod/GoogleService-Info.plist ios/Config/Dev/GoogleService-Info.plist; do
  [[ -s "$fixture_dir/$path" ]] || fail "installer did not write $path"
done

grep -q "iosBundleId: 'com.friend-app-with-wearable.ios12'," "$fixture_dir/lib/firebase_options_prod.dart" \
  || fail "prod Dart options do not name the prod iOS bundle"
grep -q "iosBundleId: 'com.friend-app-with-wearable.ios12.development'," "$fixture_dir/lib/firebase_options_dev.dart" \
  || fail "dev Dart options do not name the dev iOS bundle"
grep -q '"package_name": "com.friend.ios"' "$fixture_dir/android/app/src/prod/google-services.json" \
  || fail "prod google-services.json lacks com.friend.ios"
grep -q '"package_name": "com.friend.ios.dev"' "$fixture_dir/android/app/src/dev/google-services.json" \
  || fail "dev google-services.json lacks com.friend.ios.dev"
grep -A1 '<key>BUNDLE_ID</key>' "$fixture_dir/ios/Config/Prod/GoogleService-Info.plist" \
  | grep -q '<string>com.friend-app-with-wearable.ios12</string>' || fail "prod plist bundle id"
grep -A1 '<key>BUNDLE_ID</key>' "$fixture_dir/ios/Config/Dev/GoogleService-Info.plist" \
  | grep -q '<string>com.friend-app-with-wearable.ios12.development</string>' || fail "dev plist bundle id"

# A wrong project must be refused, not installed silently.
broken_app="$(mktemp -d "${TMPDIR:-/tmp}/omi-release-firebase-broken.XXXXXX")"
trap 'rm -rf "$fixture_dir" "$broken_app"' EXIT
mkdir -p "$broken_app/scripts" "$broken_app/setup"
cp "$ROOT_DIR/scripts/install_release_firebase_config.sh" "$broken_app/scripts/"
cp -R "$ROOT_DIR/setup/release-firebase" "$broken_app/setup/"
cp "$broken_app/setup/release-firebase/google-services.dev.json" "$broken_app/setup/release-firebase/google-services.prod.json"
if bash "$broken_app/scripts/install_release_firebase_config.sh" "$broken_app/out" >/dev/null 2>&1; then
  fail "installer accepted a dev google-services.json as prod"
fi

echo "install_release_firebase_config_test: PASS"
