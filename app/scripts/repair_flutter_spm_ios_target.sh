#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

files=(
  "$APP_ROOT/ios/Flutter/ephemeral/Packages/FlutterGeneratedPluginSwiftPackage/Package.swift"
  "$APP_ROOT/ios/Flutter/ephemeral/Packages/.packages/FlutterFramework/Package.swift"
)

for file in "${files[@]}"; do
  [[ -f "$file" ]] || continue
  perl -0pi -e 's/\.iOS\("13\.0"\)/.iOS("17.0")/g' "$file"
done

podspec="$APP_ROOT/ios/Flutter/Flutter.podspec"
if [[ -f "$podspec" ]]; then
  perl -0pi -e "s/s\\.ios\\.deployment_target = '13\\.0'/s.ios.deployment_target = '17.0'/g" "$podspec"
fi
