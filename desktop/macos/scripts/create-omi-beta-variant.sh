#!/usr/bin/env bash
# Prepare or Sparkle-package the separately installable "Omi Beta" variant.
set -euo pipefail

PHASE=""
SOURCE_APP=""
BUILD_DIR=""
BETA_APP_NAME="Omi Beta"
BETA_BUNDLE_ID="com.omi.computer-macos.beta"
SPARKLE_ZIP_OUT=""
CM_ENV_OUT=""

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/create-omi-beta-variant.sh --phase prepare \
    --source-app PATH --build-dir DIR [--beta-app-name NAME] [--beta-bundle-id ID]
  scripts/create-omi-beta-variant.sh --phase sparkle \
    --build-dir DIR --sparkle-zip-out PATH --cm-env PATH [--beta-app-name NAME]
EOF
  exit 2
}

require_value() {
  [[ $# -ge 2 && -n "$2" ]] || usage
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --phase) require_value "$@"; PHASE="$2"; shift 2 ;;
    --source-app) require_value "$@"; SOURCE_APP="$2"; shift 2 ;;
    --build-dir) require_value "$@"; BUILD_DIR="$2"; shift 2 ;;
    --beta-app-name) require_value "$@"; BETA_APP_NAME="$2"; shift 2 ;;
    --beta-bundle-id) require_value "$@"; BETA_BUNDLE_ID="$2"; shift 2 ;;
    --sparkle-zip-out) require_value "$@"; SPARKLE_ZIP_OUT="$2"; shift 2 ;;
    --cm-env) require_value "$@"; CM_ENV_OUT="$2"; shift 2 ;;
    *) usage ;;
  esac
done

[[ "$PHASE" == "prepare" || "$PHASE" == "sparkle" ]] || usage
[[ -n "$BUILD_DIR" ]] || usage
[[ -d "$BUILD_DIR" ]] || { echo "ERROR: build directory not found: $BUILD_DIR" >&2; exit 1; }
[[ "$BETA_APP_NAME" != */* && "$BETA_APP_NAME" != "." && "$BETA_APP_NAME" != ".." ]] || {
  echo "ERROR: unsafe beta app name: $BETA_APP_NAME" >&2
  exit 2
}

BETA_APP="$BUILD_DIR/$BETA_APP_NAME.app"

if [[ "$PHASE" == "prepare" ]]; then
  [[ -n "$SOURCE_APP" ]] || usage
  [[ -z "$SPARKLE_ZIP_OUT" && -z "$CM_ENV_OUT" ]] || usage
  [[ -d "$SOURCE_APP" ]] || { echo "ERROR: source app not found: $SOURCE_APP" >&2; exit 1; }
  [[ "$(cd "$SOURCE_APP" && pwd -P)" != "$(cd "$BUILD_DIR" && pwd -P)/$BETA_APP_NAME.app" ]] || {
    echo "ERROR: source app and beta destination must differ" >&2
    exit 1
  }
  : "${SIGN_IDENTITY:?SIGN_IDENTITY is required for prepare}"

  PLIST="$BETA_APP/Contents/Info.plist"
  BETA_ENV_FILE="$BETA_APP/Contents/Resources/.env"
  BETA_PYTHON_API_URL="https://api.omiapi.com/"
  BETA_DESKTOP_API_URL="https://desktop-backend-dt5lrfkkoa-uc.a.run.app/"

  echo "== Duplicating $SOURCE_APP -> $BETA_APP"
  rm -rf "$BETA_APP"
  ditto "$SOURCE_APP" "$BETA_APP"

  echo "== Patching identity and Beta authorities"
  /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $BETA_BUNDLE_ID" "$PLIST"
  /usr/libexec/PlistBuddy -c "Set :CFBundleName $BETA_APP_NAME" "$PLIST"
  /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $BETA_APP_NAME" "$PLIST"
  /usr/libexec/PlistBuddy -c \
    "Set :SUFeedURL https://api.omi.me/v2/desktop/appcast.xml?identity=beta" "$PLIST"
  [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$PLIST")" == "$BETA_BUNDLE_ID" ]]
  [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleName' "$PLIST")" == "$BETA_APP_NAME" ]]
  [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleDisplayName' "$PLIST")" == "$BETA_APP_NAME" ]]
  [[ "$(/usr/libexec/PlistBuddy -c 'Print :SUFeedURL' "$PLIST")" == \
    "https://api.omi.me/v2/desktop/appcast.xml?identity=beta" ]]

  [[ -f "$BETA_ENV_FILE" ]] || { echo "ERROR: beta bundle .env missing" >&2; exit 1; }
  sed -i '' "s|^OMI_PYTHON_API_URL=.*|OMI_PYTHON_API_URL=$BETA_PYTHON_API_URL|" "$BETA_ENV_FILE"
  sed -i '' "s|^OMI_DESKTOP_API_URL=.*|OMI_DESKTOP_API_URL=$BETA_DESKTOP_API_URL|" "$BETA_ENV_FILE"
  grep -Fqx "OMI_PYTHON_API_URL=$BETA_PYTHON_API_URL" "$BETA_ENV_FILE"
  grep -Fqx "OMI_DESKTOP_API_URL=$BETA_DESKTOP_API_URL" "$BETA_ENV_FILE"

  echo "== Re-signing outer bundle (nested signatures unchanged)"
  codesign --force --options runtime --timestamp \
    --sign "$SIGN_IDENTITY" \
    --entitlements Desktop/Omi-Release.entitlements \
    "$BETA_APP"
  codesign --verify --deep --strict --verbose=2 "$BETA_APP"
  echo "== Beta variant prepared"
  exit 0
fi

[[ -z "$SOURCE_APP" ]] || usage
[[ -n "$SPARKLE_ZIP_OUT" && -n "$CM_ENV_OUT" ]] || usage
[[ -d "$BETA_APP" ]] || { echo "ERROR: beta app not found: $BETA_APP" >&2; exit 1; }
: "${SPARKLE_PRIVATE_KEY:?SPARKLE_PRIVATE_KEY is required for sparkle}"

SPARKLE_SIGN_UPDATE="Desktop/.build/artifacts/sparkle/Sparkle/bin/sign_update"
[[ -x "$SPARKLE_SIGN_UPDATE" ]] || {
  echo "ERROR: Sparkle sign_update not found or not executable: $SPARKLE_SIGN_UPDATE" >&2
  exit 1
}

echo "== Creating beta Sparkle ZIP"
ditto -c -k --keepParent "$BETA_APP" "$SPARKLE_ZIP_OUT"
BETA_ED_SIGNATURE="$(
  printf '%s' "$SPARKLE_PRIVATE_KEY" | \
    "$SPARKLE_SIGN_UPDATE" "$SPARKLE_ZIP_OUT" --ed-key-file - 2>/dev/null | \
    sed -n 's/.*sparkle:edSignature="\([^"]*\)".*/\1/p' | head -1
)"
[[ -n "$BETA_ED_SIGNATURE" ]] || {
  echo "ERROR: could not generate EdDSA signature for the beta Sparkle ZIP" >&2
  exit 1
}
printf 'BETA_ED_SIGNATURE=%s\n' "$BETA_ED_SIGNATURE" >> "$CM_ENV_OUT"
echo "Beta EdDSA signature: $BETA_ED_SIGNATURE"
shasum -a 256 "$SPARKLE_ZIP_OUT"
