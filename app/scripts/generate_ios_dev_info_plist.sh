#!/usr/bin/env bash
set -euo pipefail

SOURCE_PLIST="${1:-ios/Runner/Info.plist}"
OUTPUT_PLIST="${2:-ios/Runner/Info-Dev.plist}"

if [[ ! -f "$SOURCE_PLIST" ]]; then
  echo "Missing source plist: $SOURCE_PLIST" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_PLIST")"
cp "$SOURCE_PLIST" "$OUTPUT_PLIST"
/usr/libexec/PlistBuddy -c 'Add :NSAppTransportSecurity dict' "$OUTPUT_PLIST"
/usr/libexec/PlistBuddy -c 'Add :NSAppTransportSecurity:NSAllowsLocalNetworking bool true' "$OUTPUT_PLIST"
plutil -lint "$OUTPUT_PLIST" >/dev/null
