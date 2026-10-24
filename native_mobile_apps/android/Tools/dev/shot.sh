#!/usr/bin/env bash
# Android screenshot of the debug app in a given state, serialized across agents (one emulator):
#   Tools/dev/shot.sh <out.png> [--apk path] [am start extras...]
# Example: Tools/dev/shot.sh /tmp/home.png --es omiTab home
# Installs the APK (default app/build/outputs/apk/debug/app-debug.apk), launches with alice signed in.
set -euo pipefail
OUT="$1"; shift
APK="$(cd "$(dirname "$0")/../.." && pwd)/app/build/outputs/apk/debug/app-debug.apk"
if [ "${1:-}" = "--apk" ]; then APK="$2"; shift 2; fi
LOCK=/tmp/omi-android-emulator.lock
until mkdir "$LOCK" 2>/dev/null; do sleep 1; done
trap 'rmdir "$LOCK"' EXIT
adb reverse tcp:8000 tcp:8000 >/dev/null; adb reverse tcp:9099 tcp:9099 >/dev/null
adb install -r "$APK" >/dev/null
adb shell am force-stop com.friend.ios.native.dev
adb shell am start -W -n com.friend.ios.native.dev/com.friend.ios.MainActivity \
  --es omiAutoSignIn alice --ez omiSkipOnboarding true "$@" >/dev/null
sleep "${OMI_SHOT_DELAY:-6}"
adb exec-out screencap -p > "$OUT"
echo "$OUT"
