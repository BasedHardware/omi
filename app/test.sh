#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

missing_files=()
required_files=(
  "lib/firebase_options_dev.dart"
  "lib/firebase_options_prod.dart"
  "lib/env/dev_env.g.dart"
  "lib/env/prod_env.g.dart"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    missing_files+=("$file")
  fi
done

if [[ ${#missing_files[@]} -gt 0 ]]; then
  echo "Missing generated files: ${missing_files[*]}"
  echo "Running setup prerequisites..."

  mkdir -p android/app/src/dev/ ios/Config/Dev/ ios/Runner/ macos/ macos/Config/Dev
  cp setup/prebuilt/firebase_options.dart lib/firebase_options_dev.dart
  cp setup/prebuilt/google-services.json android/app/src/dev/
  cp setup/prebuilt/GoogleService-Info.plist ios/Config/Dev/
  cp setup/prebuilt/GoogleService-Info.plist ios/Runner/
  cp setup/prebuilt/GoogleService-Info.plist macos/
  cp setup/prebuilt/GoogleService-Info.plist macos/Config/Dev/

  mkdir -p android/app/src/prod/ ios/Config/Prod/ macos/Config/Prod
  cp setup/prebuilt/firebase_options.dart lib/firebase_options_prod.dart
  cp setup/prebuilt/google-services.json android/app/src/prod/
  cp setup/prebuilt/GoogleService-Info.plist ios/Config/Prod/
  cp setup/prebuilt/GoogleService-Info.plist macos/Config/Prod/

  echo "API_BASE_URL=https://api.omiapi.com/" > .dev.env
  echo "USE_WEB_AUTH=true" >> .dev.env
  echo "USE_AUTH_CUSTOM_TOKEN=true" >> .dev.env

  flutter pub get
  dart run build_runner build --delete-conflicting-outputs
fi

flutter test test/providers/capture_provider_test.dart
