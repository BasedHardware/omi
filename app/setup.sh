#!/bin/bash
#
# Set up the Omi Mobile Project(iOS/Android).
#
# Prerequisites (stable versions, use these or higher):
#
# Common for all developers:
# - Flutter SDK (v3.41.9)
# - Opus Codec: https://opus-codec.org
#
# For iOS Developers:
# - Xcode (v16.4)
# - CocoaPods (v1.16.2)
#
# For Android Developers:
# - Android Studio (Iguana | 2024.3)
# - Android SDK Platform (API 35)
# - JDK (v21)
# - Gradle (v8.10)
# - NDK (28.2.13676358)
#
# Usages:
# - $bash setup.sh ios
# - $bash setup.sh android

set -euo pipefail

echo "👋 Yo folks! Welcome to the OMI Mobile Project - We're hiring! Join us on Discord: http://discord.omi.me"
echo "Prerequisites (stable versions, use these or higher):"
echo ""
echo "Common for all developers:"
echo "- Flutter SDK (v3.41.9)"
echo "- Opus Codec: https://opus-codec.org"
echo ""
echo "For iOS Developers:"
echo "- Xcode (v16.4)"
echo "- CocoaPods (v1.16.2)"
echo ""
echo "For Android Developers:"
echo "- Android Studio (Iguana | 2024.3)"
echo "- Android SDK Platform (API 36)"
echo "- JDK (v21)"
echo "- Gradle (v8.10)"
echo "- NDK (28.2.13676358)"
echo ""
echo "Usages:"
echo "- bash setup.sh ios"
echo "- bash setup.sh android"
echo ""


# Honor caller override so local-backend setup actually writes that URL to .dev.env
# (#9404 review). Default remains community remote staging.
API_BASE_URL="${API_BASE_URL:-https://api.omiapi.com/}"

######################################
# Generate device suffix from hostname
######################################
function generate_device_suffix() {
  # Use hostname or a hash of it as suffix
  HOSTNAME=$(hostname -s | tr '[:upper:]' '[:lower:]' | tr -cd '[:alnum:]')
  echo "${HOSTNAME}"
}

######################################
# Generate custom configs for iOS
######################################
function generate_ios_custom_config() {
  bash scripts/generate_ios_custom_config.sh ios/Config/Dev/GoogleService-Info.plist ios/Flutter \

  # Custom bundle identifier
  SUFFIX=$(generate_device_suffix)
  CUSTOM_BUNDLE="com.friend-app-with-wearable.ios12-${SUFFIX}"
  echo APP_BUNDLE_IDENTIFIER=${CUSTOM_BUNDLE} >> "ios/Flutter/Custom.xcconfig"
}

######################################
# Setup Firebase with prebuilt configs
######################################
function setup_firebase() {
  mkdir -p android/app/src/dev/ ios/Config/Dev/ ios/Runner/
  cp setup/prebuilt/firebase_options.dart lib/firebase_options_dev.dart
  cp setup/prebuilt/google-services.json android/app/src/dev/
  cp setup/prebuilt/GoogleService-Info.plist ios/Config/Dev/
  cp setup/prebuilt/GoogleService-Info.plist ios/Runner/

  # Warn: Mocking, should remove
  mkdir -p android/app/src/prod/ ios/Config/Prod/
  cp setup/prebuilt/firebase_options.dart lib/firebase_options_prod.dart
  cp setup/prebuilt/google-services.json android/app/src/prod/
  cp setup/prebuilt/GoogleService-Info.plist ios/Config/Prod/

  validate_firebase_api_alignment
}

##############################################################################
# Fail closed when community remote-staging API cannot verify Firebase tokens
# (#9404 / #5939). Do not text-replace project IDs — regenerate via FlutterFire.
# Compares every prebuilt artifact the app copies (json + dart + plist).
##############################################################################
function _firebase_project_id_from_prebuilt() {
  local file="$1"
  case "${file}" in
    *.json)
      grep -oE '"project_id"[[:space:]]*:[[:space:]]*"[^"]+"' "${file}" \
        | head -1 \
        | sed -E 's/.*"([^"]+)"[[:space:]]*$/\1/'
      ;;
    *.plist)
      # PROJECT_ID key followed by <string>...</string>
      tr '\n' ' ' <"${file}" \
        | grep -oE '<key>PROJECT_ID</key>[[:space:]]*<string>[^<]+</string>' \
        | head -1 \
        | sed -E 's/.*<string>([^<]+)<\/string>.*/\1/'
      ;;
    *.dart)
      # Require a single projectId across platforms in firebase_options.dart
      local ids
      ids="$(grep -oE "projectId:[[:space:]]*'[^']+'" "${file}" | sed -E "s/.*'([^']+)'.*/\1/" | sort -u)"
      if [[ "$(echo "${ids}" | grep -c .)" -eq 1 ]]; then
        echo "${ids}"
      fi
      ;;
  esac
}

function validate_firebase_api_alignment() {
  local json_proj dart_proj plist_proj project
  json_proj="$(_firebase_project_id_from_prebuilt setup/prebuilt/google-services.json)"
  dart_proj="$(_firebase_project_id_from_prebuilt setup/prebuilt/firebase_options.dart)"
  plist_proj="$(_firebase_project_id_from_prebuilt setup/prebuilt/GoogleService-Info.plist)"

  if [[ -z "${json_proj}" || -z "${dart_proj}" || -z "${plist_proj}" ]]; then
    echo "ERROR: could not parse Firebase project id from app/setup/prebuilt/* (#9404)."
    echo "  google-services.json → '${json_proj}'"
    echo "  firebase_options.dart → '${dart_proj}'"
    echo "  GoogleService-Info.plist → '${plist_proj}'"
    exit 1
  fi
  if [[ "${json_proj}" != "${dart_proj}" || "${json_proj}" != "${plist_proj}" ]]; then
    echo "ERROR: prebuilt Firebase configs disagree on project id (#9404)."
    echo "  google-services.json → '${json_proj}'"
    echo "  firebase_options.dart → '${dart_proj}'"
    echo "  GoogleService-Info.plist → '${plist_proj}'"
    echo "Regenerate the full trio via FlutterFire (do NOT text-replace — #5945)."
    exit 1
  fi
  project="${json_proj}"

  if [[ "${API_BASE_URL}" == "https://api.omiapi.com/" && "${project}" != "based-hardware" ]]; then
    echo "ERROR: Firebase project '${project}' cannot authenticate to ${API_BASE_URL}."
    echo "Community remote staging requires Firebase project 'based-hardware' (#9404)."
    echo "Tokens from '${project}' are rejected with 401 by the live backend."
    echo ""
    echo "Maintainer action: regenerate app/setup/prebuilt/* via FlutterFire against"
    echo "  based-hardware for com.friend.ios.dev / com.friend-app-with-wearable.ios12.development"
    echo "  (do NOT text-replace project IDs — closed PR #5945)."
    echo ""
    echo "Isolated local backend / emulator workaround (honors API_BASE_URL override):"
    echo "  API_BASE_URL=http://127.0.0.1:8000/ bash setup.sh ios"
    exit 1
  fi
}

######################################
# Setup provisioning profile
######################################
function setup_provisioning_profile() {
    # Only install fastlane if it doesn't exist
    if ! command -v fastlane &> /dev/null; then
        echo "Installing fastlane..."
        brew install fastlane
    fi

    MATCH_PASSWORD=omi fastlane match development --readonly \
        --app_identifier com.friend-app-with-wearable.ios12.development \
        --git_url "git@github.com:BasedHardware/omi-community-certs.git"
}


#################
# Set up App .env
#################
function setup_app_env() {
  echo API_BASE_URL=$API_BASE_URL > .dev.env
  echo USE_WEB_AUTH=true >> .dev.env
  echo USE_AUTH_CUSTOM_TOKEN=true >> .dev.env
}

# #######################
# Set up Android Keystore
# #######################
function setup_keystore_android() {
  cp setup/prebuilt/key.properties android/
}

# #####
# Build
# #####
function run_build_android() {
  flutter pub get \
    && dart run build_runner build \
    && flutter run --flavor dev
}

# #########
# Build iOS
# #########
function run_build_ios() {
  flutter pub get \
    && pushd ios && pod install --repo-update && popd \
    && dart run build_runner build \
    && flutter run --flavor dev
}


case "${1}" in
  ios)
      setup_firebase \
      && generate_ios_custom_config \
      && setup_app_env \
      && run_build_ios
    ;;
  android)
    setup_keystore_android \
      && setup_firebase \
      && setup_app_env \
      && run_build_android
    ;;
  *)
    error "Unexpected platform '${1}'"
    ;;
esac
