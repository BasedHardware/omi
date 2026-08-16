#!/bin/bash
# Clear disposable, bundle-scoped secrets before a local-harness app launch.
#
# Rebuilding the same named bundle with ad-hoc signing can leave login-keychain
# items whose TrustedApplication ACL belongs to the previous binary. Even an
# LAContext with interaction disabled cannot reliably keep SecItemCopyMatching
# from blocking on that stale ACL. Local profiles always establish a fresh
# synthetic emulator session, device identity, and local-agent token, so these
# three exact scoped items are reset after signing/install and before launch.
set -euo pipefail

TARGET="${1:?usage: omi-local-profile-keychain-reset.sh <target-bundle-id> <app-path>}"
APP_PATH="${2:?usage: omi-local-profile-keychain-reset.sh <target-bundle-id> <app-path>}"

case "$TARGET" in
  com.omi.omi-*) ;;
  *)
    echo "Refusing to reset Keychain state for non-local named bundle '$TARGET'." >&2
    exit 1
    ;;
esac

[ -d "$APP_PATH" ] || {
  echo "Cannot reset local-profile Keychain state: app is missing at $APP_PATH." >&2
  exit 1
}

FOUND_BUNDLE_ID="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$APP_PATH/Contents/Info.plist" 2>/dev/null || true)"
if [ "$FOUND_BUNDLE_ID" != "$TARGET" ]; then
  echo "Refusing to reset Keychain state: app bundle id '$FOUND_BUNDLE_ID' does not match '$TARGET'." >&2
  exit 1
fi

TEAM_ID="$(codesign -dv --verbose=4 "$APP_PATH" 2>&1 | awk -F= '/^TeamIdentifier=/{print $2; exit}')"
if [ -z "$TEAM_ID" ] || [ "$TEAM_ID" = "not set" ]; then
  TEAM_ID="adhoc.${TARGET}"
fi

BASE_SERVICES=(
  "com.omi.desktop.firebase-rest-session"
  "com.omi.desktop.local-agent-api"
  "com.omi.client-device-id"
)
ACCOUNTS=(
  "firebase-rest-tokens"
  "local-agent-api-token"
  "install-uuid"
)

for index in "${!BASE_SERVICES[@]}"; do
  service="${BASE_SERVICES[$index]}.v2.team.${TEAM_ID}.bundle.${TARGET}"
  account="${ACCOUNTS[$index]}"
  if output="$(security delete-generic-password -s "$service" -a "$account" 2>&1)"; then
    echo "Cleared local-profile Keychain item ($service/$account)"
    continue
  else
    status=$?
  fi
  if [ "$status" -eq 44 ] || [[ "$output" == *"could not be found"* ]]; then
    echo "Local-profile Keychain item already absent ($service/$account)"
    continue
  fi
  echo "Could not clear local-profile Keychain item $service/$account: $output" >&2
  exit "$status"
done
