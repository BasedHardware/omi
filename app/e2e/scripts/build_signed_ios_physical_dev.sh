#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PHYSICAL_CONFIG="${OMI_IOS_PHYSICAL_CONFIG:-${HOME}/.config/omi-mobile-test/ios-physical-test.env}"
BUILD_MODE="${OMI_IOS_BUILD_MODE:-profile}"

fail() {
  echo "signed-ios-dev build: $*" >&2
  exit 1
}

[[ -f "$PHYSICAL_CONFIG" ]] || fail "missing local physical-device config: $PHYSICAL_CONFIG"
# The ignored maintainer config owns machine/device/signing identities. They
# must never be committed to a public branch.
# shellcheck disable=SC1090
source "$PHYSICAL_CONFIG"

DEVICE_BUNDLE_ID="${OMI_IOS_DOGFOOD_BUNDLE_ID:-}"
TEAM_ID="${OMI_IOS_TEAM_ID:-}"
SIGNING_IDENTITY="${OMI_IOS_SIGNING_IDENTITY:-}"
PROFILE_SOURCE="${OMI_IOS_PROFILE_SOURCE:-}"

[[ -n "$DEVICE_BUNDLE_ID" ]] || fail "OMI_IOS_DOGFOOD_BUNDLE_ID is missing from $PHYSICAL_CONFIG"
[[ -n "$TEAM_ID" ]] || fail "OMI_IOS_TEAM_ID is missing from $PHYSICAL_CONFIG"
[[ -n "$SIGNING_IDENTITY" ]] || fail "OMI_IOS_SIGNING_IDENTITY is missing from $PHYSICAL_CONFIG"
[[ -n "$PROFILE_SOURCE" ]] || fail "OMI_IOS_PROFILE_SOURCE is missing from $PHYSICAL_CONFIG"
[[ -f "$PROFILE_SOURCE" ]] || fail "missing provisioning profile source: $PROFILE_SOURCE"
security find-identity -v -p codesigning | grep -Fq "$SIGNING_IDENTITY" || fail "missing signing identity: $SIGNING_IDENTITY"
[[ "$BUILD_MODE" == "debug" || "$BUILD_MODE" == "profile" ]] ||
  fail "OMI_IOS_BUILD_MODE must be debug or profile, got: $BUILD_MODE"

"${APP_DIR}/e2e/scripts/bootstrap_physical_dev_config.sh" "$(dirname "$PHYSICAL_CONFIG")"

# CocoaPods writes its local tool version into the tracked lockfile even when
# dependency resolution is unchanged. A physical test build must be
# repeatable and must not manufacture source changes, so restore the exact
# pre-build lockfile on every exit path.
POD_LOCK="${APP_DIR}/ios/Podfile.lock"
POD_LOCK_BACKUP="$(mktemp /private/tmp/omi-podfile-lock.XXXXXX)"
ENTITLEMENTS="$(mktemp /private/tmp/omi-ios-entitlements.XXXXXX)"
cp "$POD_LOCK" "$POD_LOCK_BACKUP"
restore_pod_lock() {
  mv "$POD_LOCK_BACKUP" "$POD_LOCK"
  rm -f "$ENTITLEMENTS"
}
trap restore_pod_lock EXIT

python3 - "$ENTITLEMENTS" "$TEAM_ID" "$DEVICE_BUNDLE_ID" <<'PY'
import plistlib
import sys
from pathlib import Path

path, team_id, bundle_id = sys.argv[1:]
application_id = f"{team_id}.{bundle_id}"
with Path(path).open("wb") as stream:
    plistlib.dump(
        {
            "application-identifier": application_id,
            "com.apple.developer.team-identifier": team_id,
            "get-task-allow": True,
            "keychain-access-groups": [application_id],
        },
        stream,
    )
PY

cd "$APP_DIR"
flutter build ios "--${BUILD_MODE}" --no-codesign --flavor dev -t lib/main.dart --dart-define OMI_BLACKBOX_HARNESS=true

UNSIGNED_APP="${APP_DIR}/build/ios/iphoneos/Runner.app"
[[ -d "$UNSIGNED_APP" ]] || fail "Flutter did not produce $UNSIGNED_APP"

ARTIFACT_ROOT="$(mktemp -d /private/tmp/omi-ios-blackbox.XXXXXX)"
SIGNED_APP="${ARTIFACT_ROOT}/OmiBlackbox.app"
mkdir "$SIGNED_APP"
rsync -a --exclude _CodeSignature --exclude embedded.mobileprovision --exclude PlugIns --exclude Watch \
  "${UNSIGNED_APP}/" "${SIGNED_APP}/"

plutil -replace CFBundleIdentifier -string "$DEVICE_BUNDLE_ID" "${SIGNED_APP}/Info.plist"
cp "$PROFILE_SOURCE" "${SIGNED_APP}/embedded.mobileprovision"

[[ "$(plutil -extract PROJECT_ID raw "${SIGNED_APP}/GoogleService-Info.plist" 2>/dev/null || true)" == "based-hardware" ]] ||
  fail "built app does not contain canonical based-hardware Firebase configuration"

while IFS= read -r framework; do
  codesign --force --sign "$SIGNING_IDENTITY" --timestamp=none "$framework"
done < <(find "${SIGNED_APP}/Frameworks" -maxdepth 2 -type d -name '*.framework' | sort)

while IFS= read -r dylib; do
  codesign --force --sign "$SIGNING_IDENTITY" --timestamp=none "$dylib"
done < <(find "${SIGNED_APP}/Frameworks" -type f -name '*.dylib' | sort)

codesign --force \
  --sign "$SIGNING_IDENTITY" \
  --timestamp=none \
  --entitlements "$ENTITLEMENTS" \
  "$SIGNED_APP"

codesign --verify --deep --strict --verbose=2 "$SIGNED_APP"

actual_bundle="$(plutil -extract CFBundleIdentifier raw "${SIGNED_APP}/Info.plist")"
[[ "$actual_bundle" == "$DEVICE_BUNDLE_ID" ]] || fail "unexpected bundle id: $actual_bundle"
codesign -d --entitlements :- "$SIGNED_APP" 2>/dev/null | grep -Fq "${TEAM_ID}.${DEVICE_BUNDLE_ID}" ||
  fail "signed app has the wrong application identifier"
[[ ! -e "${SIGNED_APP}/PlugIns" && ! -e "${SIGNED_APP}/Watch" ]] || fail "companion payload was not stripped"
if [[ "$BUILD_MODE" == "profile" ]]; then
  [[ ! -e "${SIGNED_APP}/Frameworks/App.framework/flutter_assets/kernel_blob.bin" ]] ||
    fail "profile handoff artifact still contains Flutter JIT kernel_blob.bin"
fi

echo "$SIGNED_APP"
