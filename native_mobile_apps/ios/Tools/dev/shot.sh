#!/usr/bin/env bash
# CLI screenshot of the Debug app in a given state (no tapping): shot.sh <out.png> [launch args...]
# Example: Tools/dev/shot.sh /tmp/settings.png -omiShowSettings YES
set -euo pipefail
SIM="${OMI_SIM:-Omi Native}"
BUNDLE="${OMI_SHOT_BUNDLE:-$(/usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" "$(dirname "$0")/../../build/DerivedData/Build/Products/Debug-iphonesimulator/Omi.app/Info.plist")}"
OUT="$1"; shift
UDID=$(xcrun simctl list devices | grep "$SIM (" | head -1 | grep -oE '[0-9A-F-]{36}')
xcrun simctl boot "$UDID" 2>/dev/null || true
xcrun simctl bootstatus "$UDID" -b >/dev/null
xcrun simctl launch --terminate-running-process "$UDID" "$BUNDLE" "$@" >/dev/null
sleep "${OMI_SHOT_DELAY:-5}"
xcrun simctl io "$UDID" screenshot "$OUT" >/dev/null 2>&1
echo "$OUT"
