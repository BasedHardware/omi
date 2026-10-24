#!/usr/bin/env bash
# P1 gate: a user signed in on the Flutter build stays signed in after the native app is
# installed over it (same bundle id, no uninstall). Runs on a throwaway simulator.
#
# Usage: migration-e2e.sh <Flutter Runner.app> <native Omi.app>
#   Flutter build needs --dart-define=OMI_MIGRATION_AUTOLOGIN_UID=<uid> (local spike patch) so it
#   signs in through the real local-dev path at launch. Requires the local harness (make dev-up).
set -euo pipefail
FLUTTER_APP="$1"; NATIVE_APP="$2"
BUNDLE="com.friend-app-with-wearable.ios12.development"
EMULATOR="http://127.0.0.1:9099"
UID_EXPECTED="${MIGRATION_UID:-local-dev-user}"
OUT="${OUT_DIR:-/tmp/omi-migration-e2e}"; mkdir -p "$OUT"

fail() { echo "FAIL: $*" >&2; exit 1; }
last_login() {
  curl -s -X POST -H "Authorization: Bearer owner" -H 'content-type: application/json' \
    "$EMULATOR/identitytoolkit.googleapis.com/v1/projects/demo-omi-local/accounts:query" -d '{}' |
    python3 -c "import sys,json; print(next((u.get('lastLoginAt','') for u in json.load(sys.stdin).get('userInfo',[]) if u['localId']=='$UID_EXPECTED'),''))"
}
# Read through cfprefsd (the plist on disk is flushed lazily).
pref() { xcrun simctl spawn "$SIM" defaults read "$(xcrun simctl get_app_container "$SIM" "$BUNDLE" data)/Library/Preferences/$BUNDLE" "$1" 2>/dev/null || true; }

SIM=$(xcrun simctl create "Omi Migration E2E" "iPhone 17 Pro" com.apple.CoreSimulator.SimRuntime.iOS-26-5)
trap 'xcrun simctl shutdown "$SIM" >/dev/null 2>&1; xcrun simctl delete "$SIM" >/dev/null 2>&1' EXIT
xcrun simctl boot "$SIM"; xcrun simctl bootstatus "$SIM" -b >/dev/null

echo "1. Flutter build: install, launch, sign in"
xcrun simctl install "$SIM" "$FLUTTER_APP"
xcrun simctl launch "$SIM" "$BUNDLE" >/dev/null
for _ in $(seq 1 60); do [ "$(pref flutter.uid)" = "$UID_EXPECTED" ] && break; sleep 1; done
[ "$(pref flutter.uid)" = "$UID_EXPECTED" ] || fail "Flutter build never signed in"
FLUTTER_ONBOARDED=false; [ "$(pref flutter.onboardingCompleted)" = "1" ] && FLUTTER_ONBOARDED=true
FLUTTER_CONSENT=false; [ "$(pref flutter.aiConsentGiven)" = "1" ] && FLUTTER_CONSENT=true
LOGIN_BEFORE=$(last_login)
xcrun simctl io "$SIM" screenshot "$OUT/1-flutter.png" >/dev/null 2>&1
echo "   signed in as $UID_EXPECTED, aiConsentGiven=$FLUTTER_CONSENT, onboardingCompleted=$FLUTTER_ONBOARDED"

echo "2. Native build: install over it (no uninstall), launch without debug args"
xcrun simctl terminate "$SIM" "$BUNDLE" || true
xcrun simctl install "$SIM" "$NATIVE_APP"
[ "$(pref flutter.uid)" = "$UID_EXPECTED" ] || fail "Flutter preferences lost on install"
xcrun simctl launch "$SIM" "$BUNDLE" >/dev/null
for _ in $(seq 1 20); do case "$(pref omi.debug.phase)" in ready:*|onboarding:*|consent:*|signedOut) break;; esac; sleep 1; done
PHASE=$(pref omi.debug.phase)
sleep 2; xcrun simctl io "$SIM" screenshot "$OUT/2-native.png" >/dev/null 2>&1

# Same gates as Flutter: consent first, then onboarding, then home.
EXPECTED="consent:$UID_EXPECTED"
if [ "$FLUTTER_CONSENT" = "true" ]; then
  EXPECTED="onboarding:$UID_EXPECTED"; [ "$FLUTTER_ONBOARDED" = "true" ] && EXPECTED="ready:$UID_EXPECTED"
fi
[ "$PHASE" = "$EXPECTED" ] || fail "native phase '$PHASE', expected '$EXPECTED'"
[ "$(last_login)" = "$LOGIN_BEFORE" ] || fail "native signed in again instead of reusing the Flutter session"
echo "PASS: native app resumed the Flutter session ($PHASE) without a new sign-in. Screenshots: $OUT"
