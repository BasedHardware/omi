#!/bin/bash
# iOS launch gate for EddyPhone. ANY agent (Codex, Claude, ...) that touches
# app code MUST end its session with this script printing LAUNCH GATE: PASS.
# Build success, install success, and unit tests are NOT launch proof — every
# launch-crash regression in this repo's history passed all three.
#
# What it verifies, in order:
#   1. Static launch-safety invariants (each one is a past real regression).
#   2. Profile-dev build with the DEFAULT stable Xcode (sdk < 27).
#   3. Manual wildcard signing (Xcode signing does not work for this setup).
#   4. Install on EddyPhone.
#   5. Console-attached foreground launch that SURVIVES >= 20 seconds.
#
# Usage:
#   ./scripts/verify_ios_launch.sh              # full gate (device required)
#   SKIP_DEVICE=1 ./scripts/verify_ios_launch.sh  # static checks + build only
#   SKIP_BUILD=1 ./scripts/verify_ios_launch.sh   # reuse existing build/
set -u
cd "$(dirname "$0")/.."

DEVICE=2649C7E8-7E64-501B-9108-8BC6038B8C2F
BUNDLE=dev.moni11811.omi
PROF="$HOME/Library/MobileDevice/Provisioning Profiles/48f2f131-82bb-4d61-a068-681d67c4b178.mobileprovision"
SIGN_ID=0BBD82AB2F8DE0853AC54EADEFEEEEF6D2CB1FE6
APP=build/ios/iphoneos/Runner.app
FAIL=0

say()  { printf '%s\n' "$*"; }
bad()  { say "GATE FAIL: $*"; FAIL=1; }

# --- 1. Static launch-safety invariants (each caused a real broken install) --

# UIScene opt-in makes delegate.window nil during didFinishLaunching;
# flutter_contacts force-unwraps it in register(with:) -> SIGTRAP before Dart.
grep -q "UIApplicationSceneManifest" ios/Runner/Info.plist \
  && bad "UIApplicationSceneManifest in Info.plist (crashes flutter_contacts registration; 2026-07-05)"

# DAT needs iOS 17; pub get silently resets this file to 13.0.
grep -q "s.ios.deployment_target = '17.0'" ios/Flutter/Flutter.podspec \
  || bad "ios/Flutter/Flutter.podspec deployment_target is not 17.0 (pub get reset it)"

# Envied bakes this URL into the binary; a tunnel URL means every API call dies.
grep -q "API_BASE_URL=https://api.omi.me/" .dev.env \
  || bad ".dev.env API_BASE_URL is not https://api.omi.me/ (baked into dev_env.g.dart at build time)"

# SwiftProtobuf must stay statically linked (dynamic hack = dyld launch crash).
grep -qE "^\s*use_frameworks! :linkage => :static" ios/Podfile \
  || bad "ios/Podfile lost 'use_frameworks! :linkage => :static' (SwiftProtobuf dyld crash; 2026-07-04)"

[ "$FAIL" -eq 1 ] && { say "LAUNCH GATE: FAIL (static invariants)"; exit 1; }
say "static invariants: OK"

# --- 2. Build with the DEFAULT stable Xcode ---------------------------------

if [ "${SKIP_BUILD:-0}" != "1" ]; then
  # DEVELOPER_DIR unset on purpose: Xcode-beta's iOS 27 SDK enforces UIScene
  # and old plugins crash under it. Stable Xcode (sdk 26.x) keeps the legacy
  # lifecycle on iOS 27 devices.
  env -u DEVELOPER_DIR flutter build ios --profile --flavor dev --no-codesign \
    || { say "LAUNCH GATE: FAIL (build)"; exit 1; }
fi
[ -d "$APP" ] || { say "LAUNCH GATE: FAIL ($APP missing)"; exit 1; }

SDK=$(vtool -show-build "$APP/Runner" 2>/dev/null | awk '/ sdk /{print $2; exit}')
case "$SDK" in
  27*|28*) bad "binary linked against sdk $SDK (iOS 27+ SDK requires UIScene -> plugin registration crash). Build with the default stable Xcode." ;;
  *) say "sdk check: $SDK OK" ;;
esac

otool -L "$APP/Runner" | grep -qi "SwiftProtobuf.framework" \
  && bad "Runner links @rpath/SwiftProtobuf.framework that is never embedded (dyld crash on launch)"

[ "$FAIL" -eq 1 ] && { say "LAUNCH GATE: FAIL (artifact checks)"; exit 1; }

if [ "${SKIP_DEVICE:-0}" = "1" ]; then
  say "LAUNCH GATE: PASS (static + build only; SKIP_DEVICE=1 — device launch NOT proven)"
  exit 0
fi

# --- 3. Sign (manual wildcard; Xcode signing fails for this project) --------

cp "$PROF" "$APP/embedded.mobileprovision" || { say "LAUNCH GATE: FAIL (profile copy)"; exit 1; }
cp "$PROF" "$APP/PlugIns/BatteryWidget.appex/embedded.mobileprovision"
for FW in "$APP/Frameworks/"*.framework; do
  codesign --force --sign "$SIGN_ID" --timestamp=none "$FW" >/dev/null 2>&1
done
codesign --force --sign "$SIGN_ID" --entitlements scripts/signing/ent-appex.plist --timestamp=none \
  "$APP/PlugIns/BatteryWidget.appex" >/dev/null 2>&1
codesign --force --sign "$SIGN_ID" --entitlements scripts/signing/ent-app.plist --timestamp=none \
  "$APP" >/dev/null 2>&1
codesign --verify --deep --strict "$APP" || { say "LAUNCH GATE: FAIL (codesign verify)"; exit 1; }
say "signing: OK"

# --- 4. Install --------------------------------------------------------------

xcrun devicectl device install app --device "$DEVICE" "$APP" >/dev/null 2>&1 \
  || { say "LAUNCH GATE: FAIL (install)"; exit 1; }
say "install: OK"

# --- 5. Foreground launch survival proof -------------------------------------
# Locked phone is not an app failure: retry up to ~2 min, then ask the human.
# IMPORTANT: this loop must never linger after the gate finishes; a stray
# --terminate-existing kills the user's live session (happened 2026-07-05).

OUT=$(mktemp /tmp/omi-launch-gate.XXXXXX)
LPID=""
cleanup() { [ -n "$LPID" ] && kill "$LPID" 2>/dev/null; }
trap cleanup EXIT

ATTEMPTS=0
while [ $ATTEMPTS -lt 6 ]; do
  ATTEMPTS=$((ATTEMPTS + 1))
  : > "$OUT"
  xcrun devicectl device process launch --console --terminate-existing \
    --device "$DEVICE" "$BUNDLE" > "$OUT" 2>&1 &
  LPID=$!
  sleep 20
  if grep -q "Locked" "$OUT"; then
    say "device locked (attempt $ATTEMPTS/6) — unlock EddyPhone"
    kill "$LPID" 2>/dev/null; LPID=""
    sleep 5
    continue
  fi
  if kill -0 "$LPID" 2>/dev/null; then
    kill "$LPID" 2>/dev/null; LPID=""
    say "launch survival: OK (console still attached after 20s)"
    say "LAUNCH GATE: PASS"
    exit 0
  fi
  say "app exited within 20s — console output tail:"
  tail -20 "$OUT"
  say "LAUNCH GATE: FAIL (app did not survive foreground launch)"
  exit 1
done

say "LAUNCH GATE: FAIL (device stayed locked; could not prove launch — do NOT claim the app works)"
exit 1
