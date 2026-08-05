#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG_DIR="${1:-${HOME}/.config/omi-mobile-test}"

fail() {
  echo "physical-dev bootstrap: $*" >&2
  exit 1
}

required=(
  dev.env
  firebase_options_dev.dart
  google-services.json
  GoogleService-Info.plist
  dev_env.g.dart
  prod_env.g.dart
)

for name in "${required[@]}"; do
  [[ -f "${CONFIG_DIR}/${name}" ]] || fail "missing ${CONFIG_DIR}/${name}"
done

android_project="$(jq -r '.project_info.project_id // empty' "${CONFIG_DIR}/google-services.json")"
ios_project="$(plutil -extract PROJECT_ID raw "${CONFIG_DIR}/GoogleService-Info.plist" 2>/dev/null || true)"
dart_android_project="$(
  sed -n '/static const FirebaseOptions android =/,/);/p' "${CONFIG_DIR}/firebase_options_dev.dart" |
    sed -n "s/.*projectId: '\([^']*\)'.*/\1/p"
)"
dart_ios_project="$(
  sed -n '/static const FirebaseOptions ios =/,/);/p' "${CONFIG_DIR}/firebase_options_dev.dart" |
    sed -n "s/.*projectId: '\([^']*\)'.*/\1/p"
)"

for project in "$android_project" "$ios_project" "$dart_android_project" "$dart_ios_project"; do
  [[ "$project" == "based-hardware" ]] ||
    fail "refusing non-canonical Firebase project '${project:-missing}' (expected based-hardware)"
done

mkdir -p \
  "${APP_DIR}/android/app/src/dev" \
  "${APP_DIR}/ios/Config/Dev" \
  "${APP_DIR}/ios/Runner" \
  "${APP_DIR}/lib/env"

cp "${CONFIG_DIR}/dev.env" "${APP_DIR}/.dev.env"
cp "${CONFIG_DIR}/firebase_options_dev.dart" "${APP_DIR}/lib/firebase_options_dev.dart"
android_config_tmp="$(mktemp /private/tmp/omi-google-services.XXXXXX)"
jq '
  ([.client[] | select(.client_info.android_client_info.package_name == "com.friend.ios.dev")][0]) as $source
  | if $source == null then error("canonical com.friend.ios.dev Firebase client is missing")
    else .client += [($source | .client_info.android_client_info.package_name = "com.friend.ios.dev.blackbox")]
    end
' "${CONFIG_DIR}/google-services.json" > "$android_config_tmp"
mv "$android_config_tmp" "${APP_DIR}/android/app/src/dev/google-services.json"
cp "${CONFIG_DIR}/GoogleService-Info.plist" "${APP_DIR}/ios/Config/Dev/GoogleService-Info.plist"
cp "${CONFIG_DIR}/GoogleService-Info.plist" "${APP_DIR}/ios/Runner/GoogleService-Info.plist"
cp "${CONFIG_DIR}/dev_env.g.dart" "${APP_DIR}/lib/env/dev_env.g.dart"
cp "${CONFIG_DIR}/prod_env.g.dart" "${APP_DIR}/lib/env/prod_env.g.dart"
cp "${APP_DIR}/setup/prebuilt/key.properties" "${APP_DIR}/android/key.properties"

# main.dart imports both option files even in a dev build. This is a compile-only
# stub; physical commands below must always use --flavor dev.
if [[ ! -f "${APP_DIR}/lib/firebase_options_prod.dart" ]]; then
  cp "${APP_DIR}/setup/prebuilt/firebase_options.dart" "${APP_DIR}/lib/firebase_options_prod.dart"
fi

"${APP_DIR}/scripts/verify_android_physical_test_auth_config.sh"
"${APP_DIR}/scripts/verify_ios_physical_test_auth_config.sh"

echo "physical-dev bootstrap: canonical based-hardware config installed for Android and iOS dev flavors"
