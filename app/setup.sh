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


API_BASE_URL=https://api.omiapi.com/

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


############################
# Set up public client env
############################
function setup_app_env() {
  echo PUBLIC_API_BASE_URL=$API_BASE_URL > .client.dev.env
  echo PUBLIC_USE_WEB_AUTH=true >> .client.dev.env
  echo PUBLIC_USE_AUTH_CUSTOM_TOKEN=true >> .client.dev.env
  echo PUBLIC_STAGING_API_URL= >> .client.dev.env
  cp .client.dev.env .client.env
  ../scripts/check-public-client-secrets.py --env-file .client.dev.env --env-file .client.env
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
