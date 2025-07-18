#!/bin/bash
#
# Set up the Omi Mobile Project(iOS/Android).
#
# Prerequisites (stable versions, use these or higher):
#
# Common for all developers:
# - Flutter SDK (v3.32.4)
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
# - NDK (27.0.12077973)
# Usages: 
# - $bash setup.sh ios
# - $bash setup.sh android
# - $bash setup.sh macos

set -euo pipefail

echo "👋 Yo folks! Welcome to the OMI Mobile Project - We're hiring! Join us on Discord: http://discord.omi.me"
echo "Prerequisites (stable versions, use these or higher):"
echo ""
echo "Common for all developers:"
echo "- Flutter SDK (v3.32.4)"
echo "- Opus Codec: https://opus-codec.org"
echo ""
echo "For iOS Developers:"
echo "- Xcode (v16.4)"
echo "- CocoaPods (v1.16.2)"
echo ""
echo "For Android Developers:"
echo "- Android Studio (Iguana | 2024.3)"
echo "- Android SDK Platform (API 35)"
echo "- JDK (v21)"
echo "- Gradle (v8.10)"
echo "- NDK (27.0.12077973)"
echo ""
echo "For macOS Developers:"
echo "- Xcode (v16.4)"
echo "- CocoaPods (v1.16.2)"
echo ""
echo "Usages:"
echo "- bash setup.sh ios"
echo "- bash setup.sh android"
echo "- bash setup.sh macos"
echo ""


API_BASE_URL=https://api.omiapi.com/

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
    && dart run build_runner build
}

# #########
# Build iOS
# #########
function run_build_ios() {
  flutter pub get \
    && pushd ios && pod install --repo-update && popd \
    && dart run build_runner build
}

# #########
# Build macOS
# #########
function run_build_macos() {
  flutter pub get \
    && pushd macos && pod install --repo-update && popd \
    && dart run build_runner build \
    && flutter build macos --debug --flavor dev \
    && open build/macos/Build/Products/Debug-dev/Omi.app

  echo "Note: To run the app on your macOS device, we need to register your Mac's device ID to our provisioning profile. Please send us your device ID on Discord (http://discord.omi.me)."
}


case "${1}" in
  macos)
    setup_firebase \
      && setup_app_env \
      && setup_provisioning_profile_macos \
      && run_build_macos
    ;;
  ios)
    setup_firebase \
      && setup_app_env \
      && setup_provisioning_profile \
      && run_build_ios
    ;;
  android)
    setup_keystore_android \
      && setup_firebase \
      && setup_app_env \
      && run_build_android
    ;;
  macos)
    setup_firebase \
      && setup_app_env \
      && setup_provisioning_profile \
      && build_macos
    ;;
  *)
    error "Unexpected platform '${1}'"
    ;;
esac
