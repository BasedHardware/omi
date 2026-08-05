#!/usr/bin/env bash
set -euo pipefail

PHYSICAL_CONFIG="${OMI_IOS_PHYSICAL_CONFIG:-${HOME}/.config/omi-mobile-test/ios-physical-test.env}"
APP_PATH="${1:-}"

fail() {
  echo "ios-dogfood install: $*" >&2
  exit 1
}

[[ -f "$PHYSICAL_CONFIG" ]] || fail "missing local physical-device config: $PHYSICAL_CONFIG"
# shellcheck disable=SC1090
source "$PHYSICAL_CONFIG"

DEVICE_ID="${OMI_IOS_DEVICE_ID:-}"
BUNDLE_ID="${OMI_IOS_DOGFOOD_BUNDLE_ID:-}"
TEAM_ID="${OMI_IOS_TEAM_ID:-}"
[[ -n "$DEVICE_ID" ]] || fail "OMI_IOS_DEVICE_ID is missing from $PHYSICAL_CONFIG"
[[ -n "$BUNDLE_ID" ]] || fail "OMI_IOS_DOGFOOD_BUNDLE_ID is missing from $PHYSICAL_CONFIG"
[[ -n "$TEAM_ID" ]] || fail "OMI_IOS_TEAM_ID is missing from $PHYSICAL_CONFIG"
APPLICATION_ID="${TEAM_ID}.${BUNDLE_ID}"

[[ -n "$APP_PATH" ]] || fail "usage: $0 /absolute/path/to/profile.app"
python3 "$(dirname "$0")/verify_ios_dogfood_artifact.py" \
  --app "$APP_PATH" \
  --bundle-id "$BUNDLE_ID" \
  --application-id "$APPLICATION_ID" || fail "artifact verification failed"

# Updating the exact bundle in place preserves auth, pairing, local recordings,
# and the durable sync manifest. Never uninstall to change build modes.
xcrun devicectl device install app --device "$DEVICE_ID" "$APP_PATH"
xcrun devicectl device process launch --terminate-existing --device "$DEVICE_ID" "$BUNDLE_ID"

echo "ios-dogfood install: standalone AOT app installed in place and cold-launched"
