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
echo "- bash setup.sh ios beta   # explicit production-data dogfood build"
echo ""

LOCAL_DEV_HOST="${OMI_DEV_HOST:-127.0.0.1}"
LOCAL_API_BASE_URL="${OMI_LOCAL_API_BASE_URL:-http://${LOCAL_DEV_HOST}:8000/}"
ANDROID_DEV_HOST="${OMI_ANDROID_DEV_HOST:-${OMI_DEV_HOST:-10.0.2.2}}"
ANDROID_LOCAL_API_BASE_URL="${OMI_LOCAL_API_BASE_URL:-http://${ANDROID_DEV_HOST}:8000/}"
BETA_API_BASE_URL="${OMI_BETA_API_BASE_URL:-https://api.omiapi.com/}"

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
  local config_name="${1:-Dev}"
  local callback_scheme="${2:-omi-dev}"
  bash scripts/generate_ios_custom_config.sh "ios/Config/${config_name}/GoogleService-Info.plist" ios/Flutter

  if [[ "$config_name" == "Dev" ]]; then
    # Keep ordinary local builds installable beside the App Store build.
    local suffix
    suffix=$(generate_device_suffix)
    echo "APP_BUNDLE_IDENTIFIER=com.friend-app-with-wearable.ios12-${suffix}" >> ios/Flutter/Custom.xcconfig
  else
    # Beta uses a distinct bundle/callback identity and must be provisioned
    # explicitly by the developer's Apple team.
    echo "APP_BUNDLE_IDENTIFIER=${OMI_MOBILE_BETA_BUNDLE_ID:-com.friend-app-with-wearable.ios12.beta}" >> ios/Flutter/Custom.xcconfig
    echo "AUTH_CALLBACK_SCHEME=${callback_scheme}" >> ios/Flutter/Custom.xcconfig
  fi
}

######################################
# Setup Firebase with prebuilt configs
######################################
function setup_firebase() {
  mkdir -p android/app/src/dev/ android/app/src/prod/ ios/Config/Dev/ ios/Config/Prod/ ios/Runner/
  cp setup/prebuilt/firebase_options_local.dart lib/firebase_options_dev.dart
  cp setup/prebuilt/firebase_options_local.dart lib/firebase_options_prod.dart
  cp setup/prebuilt/google-services-local.json android/app/src/dev/google-services.json
  cp setup/prebuilt/google-services-local.json android/app/src/prod/google-services.json
  cp setup/prebuilt/GoogleService-Info-Local.plist ios/Config/Dev/GoogleService-Info.plist
  cp setup/prebuilt/GoogleService-Info-Local.plist ios/Config/Prod/GoogleService-Info.plist
  cp setup/prebuilt/GoogleService-Info-Local.plist ios/Runner/GoogleService-Info.plist
}

##########################################
# Setup Firebase with Service Account Json
##########################################
function setup_firebase_with_service_account_ios() {
  dart pub global activate flutterfire_cli
  flutterfire config \
    --platforms=ios \
    --out=lib/firebase_options_prod.dart \
    --ios-bundle-id=${OMI_MOBILE_BETA_BUNDLE_ID:-com.friend-app-with-wearable.ios12.beta} \
    --ios-out=ios/Config/Prod/ \
    --service-account="$FIREBASE_SERVICE_ACCOUNT_KEY" \
    --project="based-hardware" \
    --ios-target="Runner" \
    --yes
}

function setup_firebase_with_service_account_android() {
  dart pub global activate flutterfire_cli
  flutterfire config \
    --platforms=android \
    --out=lib/firebase_options_prod.dart \
    --android-app-id=com.friend.ios \
    --android-out=android/app/src/prod/ \
    --service-account="$FIREBASE_SERVICE_ACCOUNT_KEY" \
    --project="based-hardware" \
    --yes
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
  local profile="${1:-local_dev}"
  local configured_api_base_url="${2:-}"
  local env_file='.dev.env'
  local api_base_url="${configured_api_base_url:-$LOCAL_API_BASE_URL}"
  if [[ "$profile" == "mobile_beta" ]]; then
    env_file='.env'
    api_base_url="$BETA_API_BASE_URL"
  fi
  printf 'API_BASE_URL=%s\nUSE_WEB_AUTH=true\nUSE_AUTH_CUSTOM_TOKEN=true\n' "$api_base_url" > "$env_file"
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
  local flavor="${1:-dev}"
  local profile='local_dev'
  local api_base_url="$ANDROID_LOCAL_API_BASE_URL"
  local emulator_host="$ANDROID_DEV_HOST"
  if [[ "$flavor" == "prod" ]]; then
    profile='mobile_beta'
    api_base_url="$BETA_API_BASE_URL"
    emulator_host=''
  fi
  local flutter_args=(
    --flavor "$flavor"
    "--dart-define=OMI_APP_PROFILE=$profile"
    "--dart-define=OMI_API_BASE_URL=$api_base_url"
  )
  if [[ -n "$emulator_host" ]]; then
    flutter_args+=("--dart-define=OMI_FIREBASE_AUTH_EMULATOR_HOST=$emulator_host")
  fi
  flutter pub get \
    && dart run build_runner build \
    && flutter run "${flutter_args[@]}"
}

# #########
# Build iOS
# #########
function run_build_ios() {
  local flavor="${1:-dev}"
  shift || true
  flutter pub get \
    && pushd ios && pod install --repo-update && popd \
    && dart run build_runner build \
    && flutter run --flavor "$flavor" "$@"
}


case "${1}" in
  ios)
    if [[ "${2:-}" == "beta" ]]; then
      if [[ -z "${FIREBASE_SERVICE_ACCOUNT_KEY:-}" ]]; then
        echo "ios beta requires FIREBASE_SERVICE_ACCOUNT_KEY so the production Firebase app config can be generated." >&2
        exit 1
      fi
      setup_firebase \
        && setup_firebase_with_service_account_ios \
        && generate_ios_custom_config Prod omi-beta \
        && setup_app_env mobile_beta \
        && run_build_ios prod --dart-define=OMI_APP_PROFILE=mobile_beta
    else
      setup_firebase \
        && bash scripts/generate_ios_dev_info_plist.sh \
        && generate_ios_custom_config Dev omi-dev \
        && setup_app_env local_dev \
        && run_build_ios dev \
          --dart-define=OMI_APP_PROFILE=local_dev \
          --dart-define=OMI_API_BASE_URL="$LOCAL_API_BASE_URL" \
          --dart-define=OMI_FIREBASE_AUTH_EMULATOR_HOST="$LOCAL_DEV_HOST"
    fi
    ;;
  android)
    if [[ "${2:-}" == "beta" ]]; then
      if [[ -z "${FIREBASE_SERVICE_ACCOUNT_KEY:-}" ]]; then
        echo "android beta requires FIREBASE_SERVICE_ACCOUNT_KEY so the production Firebase app config can be generated." >&2
        exit 1
      fi
      setup_keystore_android \
        && setup_firebase \
        && setup_firebase_with_service_account_android \
        && setup_app_env mobile_beta "$BETA_API_BASE_URL" \
        && run_build_android prod
    else
      setup_keystore_android \
        && setup_firebase \
        && setup_app_env local_dev "$ANDROID_LOCAL_API_BASE_URL" \
        && run_build_android dev
    fi
    ;;
  *)
    echo "Unexpected platform '${1}'" >&2
    exit 1
    ;;
esac
