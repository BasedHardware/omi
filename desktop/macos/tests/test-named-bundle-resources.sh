#!/usr/bin/env bash
# discovery-skip: needs an installed named bundle path — run it directly with the .app
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 /Applications/your-named-omi.app" >&2
  exit 64
fi

APP_BUNDLE="$1"
RESOURCE_ROOT="$APP_BUNDLE/Contents/Resources"
SWIFTPM_RESOURCES="$RESOURCE_ROOT/Omi Computer_Omi Computer.bundle"

if [[ ! -d "$APP_BUNDLE" ]]; then
  echo "FAIL: expected named app bundle at $APP_BUNDLE" >&2
  exit 1
fi

required_paths=(
  "$RESOURCE_ROOT/OmiIcon.icns"
  "$SWIFTPM_RESOURCES/herologo.png"
  "$SWIFTPM_RESOURCES/omi_text_logo.png"
  "$SWIFTPM_RESOURCES/omi_app_icon.png"
  "$SWIFTPM_RESOURCES/omi_menu_bar_icon.png"
  "$SWIFTPM_RESOURCES/hermes_logo.png"
  "$SWIFTPM_RESOURCES/openclaw_logo.png"
)

for required_path in "${required_paths[@]}"; do
  if [[ ! -s "$required_path" ]]; then
    echo "FAIL: missing or empty packaged asset: $required_path" >&2
    exit 1
  fi
done

echo "PASS: named bundle contains every Omi identity and provider-logo asset"
