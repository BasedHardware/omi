#!/bin/bash
#
# Set up the Omi Mobile Project(iOS/Android).
#
# Prerequisites (stable versions, use these or higher):
#
# Common for all developers:
# - Flutter SDK (v3.35.3)
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
# For MacOS Developers:
# - Xcode (v26.0)
# - CocoaPods (v1.16.2)
#
# Usages: 
# - $bash setup.sh ios
# - $bash setup.sh android
# - $bash setup.sh macos

set -euo pipefail

echo "👋 Yo folks! Welcome to the OMI Mobile Project - We're hiring! Join us on Discord: http://discord.omi.me"
echo "Prerequisites (stable versions, use these or higher):"
echo ""
echo "Common for all developers:"
echo "- Flutter SDK (v3.35.3)"
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
echo "For macOS Developers:"
echo "- Xcode (v26.0)"
echo "- CocoaPods (v1.16.2)"
echo ""
echo "Usages:"
echo "- bash setup.sh ios"
echo "- bash setup.sh android"
echo "- bash setup.sh macos"
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
# Generate custom configs for macOS
######################################
function generate_macos_custom_config() {
  echo "// This is a generated file; do not edit or check into version control." > "macos/Runner/Configs/Custom.xcconfig"

  # Custom bundle identifier
  SUFFIX=$(generate_device_suffix)
  CUSTOM_BUNDLE="com.friend-app-with-wearable.macos-${SUFFIX}"
  echo APP_BUNDLE_IDENTIFIER=${CUSTOM_BUNDLE} >> "macos/Runner/Configs/Custom.xcconfig"
}

######################################
# Setup Firebase with prebuilt configs
######################################
function setup_firebase() {
  mkdir -p android/app/src/dev/ ios/Config/Dev/ ios/Runner/ macos/ macos/Config/Dev
  cp setup/prebuilt/firebase_options.dart lib/firebase_options_dev.dart
  cp setup/prebuilt/google-services.json android/app/src/dev/
  cp setup/prebuilt/GoogleService-Info.plist ios/Config/Dev/
  cp setup/prebuilt/GoogleService-Info.plist ios/Runner/
  cp setup/prebuilt/GoogleService-Info.plist macos/
  cp setup/prebuilt/GoogleService-Info.plist macos/Config/Dev/

  # Warn: Mocking, should remove
  mkdir -p android/app/src/prod/ ios/Config/Prod/ macos/Config/Prod
  cp setup/prebuilt/firebase_options.dart lib/firebase_options_prod.dart
  cp setup/prebuilt/google-services.json android/app/src/prod/
  cp setup/prebuilt/GoogleService-Info.plist ios/Config/Prod/
  cp setup/prebuilt/GoogleService-Info.plist macos/Config/Prod/
}

##########################################
# Setup Firebase with Service Account Json
##########################################
function setup_firebase_with_service_account() {
  dart pub global activate flutterfire_cli
  flutterfire config \
    --platforms="android,ios,macos,web" \
    --out=lib/firebase_options_dev.dart \
    --ios-bundle-id=com.friend-app-with-wearable.ios12.development \
    --macos-bundle-id=com.friend-app-with-wearable.ios12.development \
    --android-app-id=com.friend.ios.dev \
    --android-out=android/app/src/dev/  \
    --ios-out=ios/Config/Dev/ \
    --macos-out=macos/Config/Dev/ \
    --service-account="$FIREBASE_SERVICE_ACCOUNT_KEY" \
    --project="based-hardware-dev" \
    --ios-target="Runner" \
    --macos-target="Runner" \
    --yes

  flutterfire config \
    --platforms="android,ios,macos,web" \
    --out=lib/firebase_options_prod.dart \
    --ios-bundle-id=com.friend-app-with-wearable.ios12 \
    --macos-bundle-id=com.friend-app-with-wearable.ios12 \
    --android-app-id=com.friend.ios.dev \
    --android-out=android/app/src/prod/ \
    --ios-out=ios/Config/Prod/ \
    --macos-out=macos/Config/Prod/ \
    --service-account="$FIREBASE_SERVICE_ACCOUNT_KEY" \
    --project="based-hardware-dev" \
    --ios-target="Runner" \
    --macos-target="Runner" \
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

######################################
# Setup provisioning profile macOS
######################################
function setup_provisioning_profile_macos() {
    # Only install fastlane if it doesn't exist
    if ! command -v fastlane &> /dev/null; then
        echo "Installing fastlane..."
        brew install fastlane
    fi
    
    MATCH_PASSWORD=omi fastlane match development --readonly \
        --platform macos \
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

# #########
# Build macOS
# #########
function run_build_macos() {
  flutter clean \
    && flutter pub get \
    && pushd macos && pod install --repo-update && popd \
    && dart run build_runner build

  echo ""
  echo "Setup complete! Opening Xcode..."
  echo ""
  echo "NEXT STEPS:"
  echo "1. Select 'Runner' target"
  echo "2. Go to 'Signing & Capabilities'"
  echo "3. Select your Development Team"
  echo "4. Run \$ flutter run --flavor dev --debug"
  echo ""
  sleep 3

  open macos/Runner.xcodeproj
}


case "${1}" in
  macos)
    setup_firebase \
      && generate_macos_custom_config \
      && setup_app_env \
      && run_build_macos
    ;;
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
