#!/usr/bin/env bash
# iOS reference screenshot from the iOS app on the "Omi Native" simulator, serialized across agents:
#   Tools/dev/ios_shot.sh <out.png> [iOS launch args...]
# Example: Tools/dev/ios_shot.sh /tmp/home_ios.png -omiTab home
set -euo pipefail
OUT="$1"; shift
LOCK=/tmp/omi-ios-simulator.lock
until mkdir "$LOCK" 2>/dev/null; do sleep 1; done
trap 'rmdir "$LOCK"' EXIT
# The iOS app next to this one inside the Omi repository, else the omi-native checkout.
IOS="$(cd "$(dirname "$0")/../../.." && pwd)/ios"
[ -d "$IOS" ] || IOS="$HOME/CODING/omi-native"
cd "$IOS"
OMI_SIM="Omi Native" OMI_SHOT_DELAY="${OMI_SHOT_DELAY:-10}" Tools/dev/shot.sh "$OUT" -omiAutoSignIn alice -omiSkipOnboarding YES -omiGiveConsent YES "$@"
