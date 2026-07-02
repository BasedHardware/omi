#!/bin/bash
# Re-sign a named dev bundle after run.sh packaging. Use when the final
# codesign step failed with "resource fork, Finder information, or similar
# detritus not allowed" or the app crashes with Code Signature Invalid.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="${OMI_APP_NAME:-omi-smart-routing}"
# Respect run.sh's BUILD_DIR override so this works when the bundle was staged
# outside the iCloud-synced workspace (e.g. BUILD_DIR=/tmp/... ./run.sh).
BUILD_DIR="${BUILD_DIR:-$ROOT/build}"
SRC_BUNDLE="$BUILD_DIR/${APP_NAME}.app"
DEST_BUNDLE="/Applications/${APP_NAME}.app"
SIGN_IDENTITY="${OMI_SIGN_IDENTITY:-$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | sed 's/.*"\(.*\)"/\1/')}"
ENTITLEMENTS="/tmp/omi-local-dev.entitlements"
CLEAN_BUNDLE="${TMPDIR:-/tmp}/omi-sign-${APP_NAME}.app"

if [ ! -d "$SRC_BUNDLE" ]; then
  echo "ERROR: Bundle not found: $SRC_BUNDLE"
  echo "Run: OMI_APP_NAME=\"$APP_NAME\" ./run.sh --yolo"
  exit 1
fi

if [ -z "$SIGN_IDENTITY" ]; then
  echo "ERROR: No Apple Development signing identity found."
  exit 1
fi

echo "Using identity: $SIGN_IDENTITY"
cp "$ROOT/Desktop/Omi.entitlements" "$ENTITLEMENTS"
/usr/libexec/PlistBuddy -c "Delete :com.apple.developer.applesignin" "$ENTITLEMENTS" 2>/dev/null || true

rm -rf "$CLEAN_BUNDLE"
ditto --norsrc "$SRC_BUNDLE" "$CLEAN_BUNDLE"
chmod -R u+w "$CLEAN_BUNDLE"
xattr -cr "$CLEAN_BUNDLE"

sign_if_exists() {
  local path="$1"
  local entitlements="${2:-}"
  if [ -e "$path" ]; then
    echo "Signing $path"
    if [ -n "$entitlements" ]; then
      codesign --force --options runtime --entitlements "$entitlements" --sign "$SIGN_IDENTITY" "$path"
    else
      codesign --force --options runtime --sign "$SIGN_IDENTITY" "$path"
    fi
  fi
}

sign_if_exists "$CLEAN_BUNDLE/Contents/Frameworks/Sparkle.framework"
sign_if_exists "$CLEAN_BUNDLE/Contents/Frameworks/Sentry.framework"
sign_if_exists "$CLEAN_BUNDLE/Contents/Frameworks/onnxruntime.framework"
sign_if_exists "$CLEAN_BUNDLE/Contents/Frameworks/libsharpyuv.0.dylib"
sign_if_exists "$CLEAN_BUNDLE/Contents/Frameworks/libwebp.7.dylib"
sign_if_exists "$CLEAN_BUNDLE/Contents/Resources/Omi Computer_Omi Computer.bundle/node" "$ROOT/Desktop/Node.entitlements"

chmod -R u+w "$CLEAN_BUNDLE"
xattr -cr "$CLEAN_BUNDLE"
echo "Signing app bundle"
codesign --force --options runtime --entitlements "$ENTITLEMENTS" --sign "$SIGN_IDENTITY" "$CLEAN_BUNDLE"

codesign --verify --deep --strict "$CLEAN_BUNDLE"
echo "Signature OK"

rm -rf "$DEST_BUNDLE"
ditto "$CLEAN_BUNDLE" "$DEST_BUNDLE"
echo "Installed to $DEST_BUNDLE"
open "$DEST_BUNDLE"
