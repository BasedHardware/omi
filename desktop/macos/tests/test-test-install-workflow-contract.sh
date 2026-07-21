#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKFLOW="$SCRIPT_DIR/../.github/workflows/test-install.yml"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

require_text() {
  local pattern="$1"
  grep -Fq -- "$pattern" "$WORKFLOW" || fail "install workflow missing: $pattern"
}

require_text '--pattern "omi.dmg"'
require_text 'DMG_PATH="$DOWNLOAD_DIR/omi.dmg"'
require_text 'xattr -d com.apple.quarantine "$DMG_PATH"'
require_text 'hdiutil attach "$DMG_PATH" -nobrowse -readonly -mountpoint "$MOUNTPOINT"'
require_text 'DEVICE=$(hdiutil attach'
require_text 'hdiutil detach "$DEVICE" -quiet'
require_text 'trap cleanup EXIT'
require_text 'ditto "$MOUNTPOINT/Omi.app" "/Applications/Omi.app"'

if grep -Fq '/Volumes/Omi' "$WORKFLOW"; then
  fail "install workflow must not discover or detach a pre-existing /Volumes/Omi mount"
fi
if grep -Fq -- '--pattern "Omi.dmg"' "$WORKFLOW"; then
  fail "install workflow must download only the lowercase canonical DMG"
fi

echo "test-install workflow exact-DMG contract passed"
