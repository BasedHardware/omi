#!/usr/bin/env bash
# Create the separately-installable "Omi Beta" variant from the signed stable app.
#
# The variant is the same binary re-identified (CFBundleIdentifier
# com.omi.computer-macos.beta + "Omi Beta" name) so it runs beside stable with its
# own UserDefaults, TCC grants, Keychain ACL, storage root, and single-instance
# lock. Only the outer bundle signature covers Info.plist, so nested component
# signatures from the stable signing pass remain valid; the outer bundle is
# re-signed, then the variant is independently notarized, stapled, packaged as a
# Sparkle ZIP + DMG, and EdDSA-signed for the appcast.
#
# Required env (provided by the Codemagic release workflow):
#   SIGN_IDENTITY, APP_STORE_CONNECT_KEY_IDENTIFIER, APP_STORE_CONNECT_PRIVATE_KEY,
#   APP_STORE_CONNECT_ISSUER_ID, SPARKLE_PRIVATE_KEY, DMGBUILD_VERSION
set -euo pipefail

SOURCE_APP=""
BUILD_DIR=""
BETA_APP_NAME="Omi Beta"
BETA_BUNDLE_ID="com.omi.computer-macos.beta"
SPARKLE_ZIP_OUT=""
DMG_OUT=""
CM_ENV_OUT=""

usage() {
  cat <<'EOF'
Usage: scripts/create-omi-beta-variant.sh --source-app build/omi.app --build-dir build \
  --sparkle-zip-out build/Omi.Beta.zip --dmg-out build/omi-beta.dmg [--cm-env "$CM_ENV"]
  [--beta-app-name "Omi Beta"] [--beta-bundle-id com.omi.computer-macos.beta]
EOF
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-app) SOURCE_APP="$2"; shift 2 ;;
    --build-dir) BUILD_DIR="$2"; shift 2 ;;
    --beta-app-name) BETA_APP_NAME="$2"; shift 2 ;;
    --beta-bundle-id) BETA_BUNDLE_ID="$2"; shift 2 ;;
    --sparkle-zip-out) SPARKLE_ZIP_OUT="$2"; shift 2 ;;
    --dmg-out) DMG_OUT="$2"; shift 2 ;;
    --cm-env) CM_ENV_OUT="$2"; shift 2 ;;
    *) usage ;;
  esac
done

[[ -n "$SOURCE_APP" && -n "$BUILD_DIR" && -n "$SPARKLE_ZIP_OUT" && -n "$DMG_OUT" ]] || usage
[[ -d "$SOURCE_APP" ]] || { echo "ERROR: source app not found: $SOURCE_APP" >&2; exit 1; }
: "${SIGN_IDENTITY:?SIGN_IDENTITY is required}"
: "${APP_STORE_CONNECT_KEY_IDENTIFIER:?notary key id required}"
: "${APP_STORE_CONNECT_PRIVATE_KEY:?notary private key required}"
: "${APP_STORE_CONNECT_ISSUER_ID:?notary issuer required}"
: "${SPARKLE_PRIVATE_KEY:?Sparkle EdDSA key required}"

BETA_APP="$BUILD_DIR/$BETA_APP_NAME.app"
PLIST="$BETA_APP/Contents/Info.plist"

notarize_and_staple() {
  local artifact="$1"
  mkdir -p ~/private_keys
  local key_path=~/private_keys/AuthKey_${APP_STORE_CONNECT_KEY_IDENTIFIER}.p8
  echo -e "$APP_STORE_CONNECT_PRIVATE_KEY" > "$key_path"

  local result status submission_id
  result=$(xcrun notarytool submit "$artifact" \
    --key "$key_path" \
    --key-id "$APP_STORE_CONNECT_KEY_IDENTIFIER" \
    --issuer "$APP_STORE_CONNECT_ISSUER_ID" \
    --wait \
    --output-format json)
  status=$(echo "$result" | python3 -c \
    "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
  submission_id=$(echo "$result" | python3 -c \
    "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")
  if [[ "$status" != "Accepted" ]]; then
    echo "ERROR: notarization failed for $artifact: $status" >&2
    [[ -n "$submission_id" ]] && xcrun notarytool log "$submission_id" \
      --key "$key_path" \
      --key-id "$APP_STORE_CONNECT_KEY_IDENTIFIER" \
      --issuer "$APP_STORE_CONNECT_ISSUER_ID" || true
    exit 1
  fi
}

echo "== Duplicating $SOURCE_APP -> $BETA_APP"
rm -rf "$BETA_APP"
ditto "$SOURCE_APP" "$BETA_APP"

echo "== Patching identity"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $BETA_BUNDLE_ID" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleName $BETA_APP_NAME" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $BETA_APP_NAME" "$PLIST"
# Identity-aware feed: the backend serves beta-channel items with beta-identity
# enclosures only to clients that ask with identity=beta. Legacy stable-identity
# installs keep the plain URL and their current update behavior.
/usr/libexec/PlistBuddy -c \
  "Set :SUFeedURL https://api.omi.me/v2/desktop/appcast.xml?identity=beta" "$PLIST"

echo "== Re-signing outer bundle (nested signatures unchanged)"
codesign --force --options runtime --timestamp \
  --sign "$SIGN_IDENTITY" \
  --entitlements Desktop/Omi-Release.entitlements \
  "$BETA_APP"
codesign --verify --deep --strict --verbose=2 "$BETA_APP"

echo "== Notarizing beta app"
TEMP_ZIP="$BUILD_DIR/notarize-beta-temp.zip"
ditto -c -k --keepParent "$BETA_APP" "$TEMP_ZIP"
notarize_and_staple "$TEMP_ZIP"
rm -f "$TEMP_ZIP"
xcrun stapler staple "$BETA_APP"

echo "== Creating beta DMG"
pip3 install --break-system-packages "dmgbuild==${DMGBUILD_VERSION:?}" >/dev/null
STAGING_DIR="/tmp/omi-beta-dmg-staging-$$"
mkdir -p "$STAGING_DIR"
ditto "$BETA_APP" "$STAGING_DIR/$BETA_APP_NAME.app"
xcrun stapler validate "$STAGING_DIR/$BETA_APP_NAME.app" 2>/dev/null || \
  xcrun stapler staple "$STAGING_DIR/$BETA_APP_NAME.app"
dmgbuild -s dmg-assets/dmgbuild_settings.py \
  -D app_path="$STAGING_DIR/$BETA_APP_NAME.app" \
  -D app_name="$BETA_APP_NAME" \
  -D assets_dir="$(pwd)/dmg-assets" \
  "$BETA_APP_NAME" \
  "$DMG_OUT"
rm -rf "$STAGING_DIR"

codesign --force --sign "$SIGN_IDENTITY" "$DMG_OUT"
echo "== Notarizing beta DMG"
notarize_and_staple "$DMG_OUT"
xcrun stapler staple "$DMG_OUT"

echo "== Creating beta Sparkle ZIP"
ditto -c -k --keepParent "$BETA_APP" "$SPARKLE_ZIP_OUT"
SPARKLE_BIN="Desktop/.build/artifacts/sparkle/Sparkle/bin"
BETA_ED_SIGNATURE=""
if [[ -f "$SPARKLE_BIN/sign_update" ]]; then
  BETA_ED_SIGNATURE=$(echo "$SPARKLE_PRIVATE_KEY" | \
    "$SPARKLE_BIN/sign_update" "$SPARKLE_ZIP_OUT" --ed-key-file - 2>/dev/null | \
    grep "sparkle:edSignature" | \
    sed 's/.*edSignature="\([^"]*\)".*/\1/')
fi
if [[ -z "$BETA_ED_SIGNATURE" ]]; then
  echo "ERROR: could not generate EdDSA signature for the beta Sparkle ZIP" >&2
  exit 1
fi
echo "Beta EdDSA signature: $BETA_ED_SIGNATURE"
if [[ -n "$CM_ENV_OUT" ]]; then
  echo "BETA_ED_SIGNATURE=$BETA_ED_SIGNATURE" >> "$CM_ENV_OUT"
fi

echo "== Beta variant ready"
shasum -a 256 "$SPARKLE_ZIP_OUT" "$DMG_OUT"
