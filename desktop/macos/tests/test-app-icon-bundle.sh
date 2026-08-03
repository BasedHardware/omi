#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN="$MACOS_DIR/run.sh"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-app-icon.XXXXXX")"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

ICON_COPY_FUNCTION="$(sed -n '/^copy_app_icon()/,/^}/p' "$RUN")"
if [[ -z "$ICON_COPY_FUNCTION" ]]; then
  echo "FAIL: copy_app_icon is missing from $RUN" >&2
  exit 1
fi

APP_BUNDLE="$TMP_ROOT/omi-icon-contract.app"
mkdir -p "$APP_BUNDLE/Contents/Resources"
SCRIPT_DIR="$MACOS_DIR"
eval "$ICON_COPY_FUNCTION"

copy_app_icon
cmp "$MACOS_DIR/omi_icon.icns" "$APP_BUNDLE/Contents/Resources/OmiIcon.icns"

# A caller outside desktop/macos previously made the relative copy fail and
# silently shipped a generic icon. The failure must now be explicit.
SCRIPT_DIR="$TMP_ROOT/missing-launcher-root"
if copy_app_icon >"$TMP_ROOT/missing.out" 2>"$TMP_ROOT/missing.err"; then
  echo "FAIL: missing app icon source unexpectedly succeeded" >&2
  exit 1
fi
grep -Fq "missing app icon at $SCRIPT_DIR/omi_icon.icns" "$TMP_ROOT/missing.err"

echo "PASS: named bundles receive the canonical Omi icon and missing assets fail loud"
