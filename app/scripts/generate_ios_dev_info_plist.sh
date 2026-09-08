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
# NSAllowsArbitraryLoads, not NSAllowsLocalNetworking: the latter covers only
# .local/unqualified/link-local hosts, never a Tailscale CGNAT address
# (100.64.0.0/10), which is what the documented local-dev device setup uses.
# See #11730/#11652/#11782 — a prior version of this script wrote
# NSAllowsLocalNetworking and silently reverted the CGNAT fix on every run.
/usr/libexec/PlistBuddy -c 'Add :NSAppTransportSecurity dict' "$OUTPUT_PLIST"
/usr/libexec/PlistBuddy -c 'Add :NSAppTransportSecurity:NSAllowsArbitraryLoads bool true' "$OUTPUT_PLIST"
plutil -lint "$OUTPUT_PLIST" >/dev/null
