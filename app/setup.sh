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
# Usages:
# - $bash setup.sh ios
# - $bash setup.sh android

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
# Detect Apple Development Team ID
######################################
function detect_apple_team_id() {
  # 1. Honour explicit override
  if [ -n "${APPLE_DEVELOPMENT_TEAM:-}" ]; then
    echo "$APPLE_DEVELOPMENT_TEAM"
    return
  fi

  local profiles_dir="$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles"
  local suffix
  suffix=$(generate_device_suffix)
  local bundle_pattern="com.friend-app-with-wearable.ios12-${suffix}"

  # 2. Look for a profile whose AppID matches this machine's bundle ID
  local team_id=""
  if [ -d "$profiles_dir" ]; then
    while IFS= read -r -d '' profile; do
      local plist
      plist=$(security cms -D -i "$profile" 2>/dev/null) || continue
      local app_id
      app_id=$(echo "$plist" | xmllint --xpath \
        "string(//key[text()='application-identifier']/following-sibling::string[1])" \
        - 2>/dev/null)
      local bare_id="${app_id#*.}"
      if [ "$bare_id" = "$bundle_pattern" ]; then
        team_id=$(echo "$plist" | xmllint --xpath \
          "string(//key[text()='TeamIdentifier']/following-sibling::array[1]/string[1])" \
          - 2>/dev/null)
        break
      fi
    done < <(find "$profiles_dir" -name '*.mobileprovision' -print0 2>/dev/null)
  fi

  # 3. Fallback: collect all team IDs that have a valid signing cert in the keychain
  if [ -z "$team_id" ] && [ -d "$profiles_dir" ]; then
    local seen_teams=()
    while IFS= read -r -d '' profile; do
      local plist candidate
      plist=$(security cms -D -i "$profile" 2>/dev/null) || continue
      candidate=$(echo "$plist" | xmllint --xpath \
        "string(//key[text()='TeamIdentifier']/following-sibling::array[1]/string[1])" \
        - 2>/dev/null)
      if [ -n "$candidate" ]; then
        if security find-identity -v -p codesigning 2>/dev/null | grep -q "$candidate"; then
          local already_seen=false
          for t in "${seen_teams[@]:-}"; do [ "$t" = "$candidate" ] && already_seen=true && break; done
          $already_seen || seen_teams+=("$candidate")
        fi
      fi
    done < <(find "$profiles_dir" -name '*.mobileprovision' -print0 2>/dev/null)

    if [ "${#seen_teams[@]}" -eq 1 ]; then
      team_id="${seen_teams[0]}"
    elif [ "${#seen_teams[@]}" -gt 1 ]; then
      echo "⚠️  Multiple Apple Developer accounts found. Choose one:" >&2
      for i in "${!seen_teams[@]}"; do
        echo "   $((i+1))) ${seen_teams[$i]}" >&2
      done
      local choice
      read -rp "   Enter number [1-${#seen_teams[@]}]: " choice
      if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "${#seen_teams[@]}" ]; then
        team_id="${seen_teams[$((choice-1))]}"
      fi
    fi
  fi

  # 4. Last resort: prompt the user (with format validation)
  if [ -z "$team_id" ]; then
    echo "⚠️  Could not auto-detect your Apple Development Team ID." >&2
    echo "   Find it at: https://developer.apple.com/account -> Membership" >&2
    echo "   or run: APPLE_DEVELOPMENT_TEAM=XXXXXXXXXX bash setup.sh ios" >&2
    while true; do
      read -rp "   Enter your Team ID (10 uppercase alphanumeric characters): " team_id
      team_id=$(echo "${team_id}" | tr '[:lower:]' '[:upper:]' | tr -d ' ')
      if [[ "$team_id" =~ ^[A-Z0-9]{10}$ ]]; then
        break
      fi
      echo "   ❌ Invalid Team ID '${team_id}' — must be exactly 10 uppercase letters/digits." >&2
    done
  fi

  echo "$team_id"
}

######################################
# Generate custom configs for iOS
######################################
function generate_ios_custom_config() {
  bash scripts/generate_ios_custom_config.sh ios/Config/Dev/GoogleService-Info.plist ios/Flutter \

  # Custom bundle identifier and app group
  SUFFIX=$(generate_device_suffix)
  CUSTOM_BUNDLE="com.friend-app-with-wearable.ios12-${SUFFIX}"
  CUSTOM_GROUP="group.com.friend-app-with-wearable.ios12-${SUFFIX}"
  echo APP_BUNDLE_IDENTIFIER=${CUSTOM_BUNDLE} >> "ios/Flutter/Custom.xcconfig"
  echo APP_GROUP_IDENTIFIER=${CUSTOM_GROUP} >> "ios/Flutter/Custom.xcconfig"

  # Detect and write the Development Team ID for iOS automatic signing
  echo "🔍 Detecting Apple Development Team ID..."
  DEVELOPMENT_TEAM=$(detect_apple_team_id)
  echo "✅ Team ID: ${DEVELOPMENT_TEAM}"
  echo "DEVELOPMENT_TEAM=${DEVELOPMENT_TEAM}" >> "ios/Flutter/Custom.xcconfig"
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

##########################################
# Setup Firebase with Service Account Json
##########################################
function setup_firebase_with_service_account() {
  dart pub global activate flutterfire_cli
  flutterfire config \
    --platforms="android,ios,web" \
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
    --platforms="android,ios,web" \
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
