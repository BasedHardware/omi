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
# An E2E pool slot is not a local-emulator profile. Its Keychain item holds the
# session a human signed in once, and that session must survive every rebuild —
# resetting it turns a leased slot cold for every later lane. Refuse pool slot
# ids outright (any slot number, the default prefix or the configured one);
# there is no override because there is no correct use. run.sh only calls this
# for local-profile launches; a pool slot never qualifies.
E2E_POOL_PREFIX="${OMI_E2E_POOL_PREFIX:-omi-e2e}"
for pool_prefix in omi-e2e "$E2E_POOL_PREFIX"; do
  case "$TARGET" in
    com.omi."$pool_prefix"-*)
      suffix="${TARGET#com.omi."$pool_prefix"-}"
      case "$suffix" in
        ''|*[!0-9]*) ;;  # not a bare slot number: not a pool slot
        *)
          echo "Refusing to reset Keychain state for '$TARGET': it names an E2E pool slot, not a local-emulator profile. Pool slots keep the session a human signed in once; sign in via the GUI instead (desktop/macos/scripts/omi-e2e-pool setup)." >&2
          exit 1
          ;;
      esac
      ;;
  esac
done

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
