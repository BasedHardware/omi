#!/bin/bash
#
# Set up the Omi Mobile Project(iOS/Android).
# Prerequisites:
# - Flutter SDK
# - Dart SDK
# - Xcode (for iOS)
# - CocoaPods (for iOS dependencies)
# - Android Studio (for Android)
# - NDK 26.3.11579264 or above (to build Opus for ARM Devices)
# - Opus Codec: https://opus-codec.org
# Usages: 
# - $bash setup.sh ios
# - $bash setup.sh android

set -euo pipefail

echo "👋 Yo folks! Welcome to the OMI Mobile Project - We're hiring! Join us on Discord: http://discord.omi.me"
echo "Prerequisites:"
echo "- Flutter SDK"
echo "- Dart SDK"
echo "- Xcode (for iOS)"
echo "- CocoaPods (for iOS dependencies)"
echo "- Android Studio (for Android)"
echo "- NDK 26.3.11579264 or above (to build Opus for ARM Devices)"
echo "- Opus Codec: https://opus-codec.org"
echo "Usages:"
echo "- bash setup.sh ios"
echo "- bash setup.sh android"
echo ""


API_BASE_URL=https://backend-dt5lrfkkoa-uc.a.run.app/

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

##########################################
# Setup Firebase with Service Account Json
##########################################
function setup_firebase_with_service_account() {
  dart pub global activate flutterfire_cli
  flutterfire config \
    --platforms="android,ios" \
    --out=lib/firebase_options_dev.dart \
    --ios-bundle-id=com.friend-app-with-wearable.ios12.development \
    --android-app-id=com.friend.ios.dev \
    --android-out=android/app/src/dev/  \
    --ios-out=ios/Config/Dev/ \
    --service-account="$FIREBASE_SERVICE_ACCOUNT_KEY" \
    --project="based-hardware-dev" \
    --ios-target="Runner" \
    --yes

  flutterfire config \
    --platforms="android,ios" \
    --out=lib/firebase_options_prod.dart \
    --ios-bundle-id=com.friend-app-with-wearable.ios12 \
    --android-app-id=com.friend.ios.dev \
    --android-out=android/app/src/prod/ \
    --ios-out=ios/Config/Prod/ \
    --service-account="$FIREBASE_SERVICE_ACCOUNT_KEY" \
    --project="based-hardware-dev" \
    --ios-target="Runner" \
    --yes
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
function build() {
  flutter pub get \
    && dart run build_runner build
}

# #########
# Build iOS
# #########
function build_ios() {
  flutter pub get \
    && pushd ios && pod install --repo-update && popd \
    && dart run build_runner build
}

# #######
# Run dev
# #######
function run_dev() {
  flutter run --flavor dev
}

case "${1}" in
  ios)
    setup_firebase \
      && setup_app_env \
      && build_ios
    ;;
  android)
    setup_keystore_android \
      && setup_firebase \
      && setup_app_env \
      && build
    ;;
  *)
    error "Unexpected platform '${1}'"
    ;;
esac
