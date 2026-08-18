#!/bin/bash
#
# Set up the Omi Mobile Project(iOS/Android).
#
# Prerequisites (stable versions, use these or higher):
#
# Common for all developers:
# - Flutter SDK (v3.44.5)
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
echo "- Flutter SDK (v3.44.5)"
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
echo "- bash setup.sh android beta   # explicit production-data dogfood build"
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
    # The prebuilt/placeholder GoogleService-Info.plist (setup_firebase) carries the
    # stock unsuffixed BUNDLE_ID. Firebase's native SDK validates that field against
    # the running app's actual bundle identifier at Firebase.initializeApp() and
    # refuses to start if they don't match. Runner/GoogleService-Info.plist is what
    # Xcode actually bundles (project.pbxproj references that path directly, not
    # Config/Dev/); patch both so on-disk copies stay consistent.
    local suffixed_bundle_id="com.friend-app-with-wearable.ios12-${suffix}"
    /usr/libexec/PlistBuddy -c "Set :BUNDLE_ID ${suffixed_bundle_id}" "ios/Config/${config_name}/GoogleService-Info.plist"
    /usr/libexec/PlistBuddy -c "Set :BUNDLE_ID ${suffixed_bundle_id}" ios/Runner/GoogleService-Info.plist
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
  cp lib/firebase_options_local.dart lib/firebase_options_dev.dart
  cp lib/firebase_options_local.dart lib/firebase_options_prod.dart
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

  # Keep developer-owned settings and comments intact. These are the only keys
  # owned by setup, so update them in place and replace the file atomically.
  local temp_file source_file="/dev/null"
  if [[ -f "$env_file" ]]; then source_file="$env_file"; fi
  temp_file=$(mktemp "${env_file}.tmp.XXXXXX")
  if ! awk \
    -v api_base_url="$api_base_url" \
    'BEGIN { api_written = 0; web_auth_written = 0; custom_token_written = 0 }
     /^[[:space:]]*API_BASE_URL[[:space:]]*=/ {
       if (!api_written) { print "API_BASE_URL=" api_base_url; api_written = 1 }
       next
     }
     /^[[:space:]]*USE_WEB_AUTH[[:space:]]*=/ {
       if (!web_auth_written) { print "USE_WEB_AUTH=true"; web_auth_written = 1 }
       next
     }
     /^[[:space:]]*USE_AUTH_CUSTOM_TOKEN[[:space:]]*=/ {
       if (!custom_token_written) { print "USE_AUTH_CUSTOM_TOKEN=true"; custom_token_written = 1 }
       next
     }
     { print }
     END {
       if (!api_written) print "API_BASE_URL=" api_base_url
       if (!web_auth_written) print "USE_WEB_AUTH=true"
       if (!custom_token_written) print "USE_AUTH_CUSTOM_TOKEN=true"
     }' \
    "$source_file" 2>/dev/null >"$temp_file"; then
    rm -f "$temp_file"
    return 1
  fi
  if ! mv "$temp_file" "$env_file"; then
    rm -f "$temp_file"
    return 1
  fi
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

# #####################################
# iOS prerequisite and device selection
# #####################################

# True if $1 (a dotted version, e.g. "16.4") is >= $2. Relies on `sort -V`,
# which Apple's /usr/bin/sort on macOS supports (verified; this is iOS-only
# tooling, so a non-macOS sort is not a concern).
function _version_at_least() {
  local have="$1" want="$2"
  [ "$(printf '%s\n%s\n' "$want" "$have" | sort -V | head -n1)" = "$want" ]
}

# Named checks with remedies, matching the harness's own pattern
# (scripts/dev-harness's `Cannot start; missing prerequisites:` block) instead
# of letting a missing/outdated tool surface as a confusing downstream failure
# several minutes into a build.
function check_ios_prerequisites() {
  local missing=()

  local flutter_version
  flutter_version=$(flutter --version 2>/dev/null | grep -oE '^Flutter [0-9]+\.[0-9]+\.[0-9]+' | awk '{print $2}')
  if [[ -z "$flutter_version" ]]; then
    missing+=("Flutter SDK (v3.44.5 or later) — install from https://docs.flutter.dev/get-started/install")
  elif ! _version_at_least "$flutter_version" "3.44.5"; then
    missing+=("Flutter ${flutter_version} found, but v3.44.5 or later is required — run: flutter upgrade")
  fi

  if ! command -v xcodebuild &>/dev/null; then
    missing+=("Xcode (v16.4 or later) — install from the App Store, then run: sudo xcode-select --switch /Applications/Xcode.app")
  else
    local xcode_version
    xcode_version=$(xcodebuild -version 2>/dev/null | awk '/^Xcode/ {print $2; exit}')
    if [[ -z "$xcode_version" ]]; then
      # xcodebuild is on PATH but produced no version line — an unaccepted
      # license or missing components, not a real "Xcode is fine" signal.
      # Left unchecked, this passes the gate silently and surfaces as a
      # confusing failure deep into the build, exactly what this check exists
      # to prevent.
      missing+=("xcodebuild is on PATH but not usable (license not accepted or components missing) — run: sudo xcodebuild -license accept && sudo xcodebuild -runFirstLaunch")
    elif ! _version_at_least "$xcode_version" "16.4"; then
      missing+=("Xcode ${xcode_version} found, but v16.4 or later is required — update via the App Store")
    fi
  fi

  if ! command -v pod &>/dev/null; then
    missing+=("CocoaPods (v1.16.2 or later) — install with: sudo gem install cocoapods")
  else
    local pod_version
    pod_version=$(pod --version 2>/dev/null)
    if [[ -n "$pod_version" ]] && ! _version_at_least "$pod_version" "1.16.2"; then
      missing+=("CocoaPods ${pod_version} found, but v1.16.2 or later is required — update with: brew upgrade cocoapods (Homebrew) or sudo gem install cocoapods (gem)")
    fi
  fi

  if ! command -v jq &>/dev/null; then
    missing+=("jq (used to select an iOS build destination) — install with: brew install jq")
  fi

  if [[ "${#missing[@]}" -gt 0 ]]; then
    echo "❌ Cannot build for iOS; missing prerequisites:" >&2
    local item
    for item in "${missing[@]}"; do
      echo "   - ${item}" >&2
    done
    return 1
  fi
}

# Picks the iOS destination `flutter run -d` should target, instead of leaving
# Flutter to fall back to whatever else it finds (macOS desktop, on a machine
# with no simulator runtime and only a wirelessly-paired phone visible) and
# reporting an error about a platform the developer never asked for.
function select_ios_device() {
  local devices_json
  devices_json=$(flutter devices --machine 2>/dev/null) || {
    echo "❌ Could not query connected devices (flutter devices --machine failed)." >&2
    return 1
  }

  local ios_devices
  ios_devices=$(echo "$devices_json" | jq -c '[.[] | select(.targetPlatform == "ios")]')
  local count
  count=$(echo "$ios_devices" | jq 'length')

  if [[ "$count" -eq 0 ]]; then
    echo "❌ No iOS device or simulator found." >&2
    echo "   Boot a simulator (open -a Simulator) or connect a physical device, then retry." >&2
    return 1
  fi

  if [[ "$count" -eq 1 ]]; then
    echo "$ios_devices" | jq -r '.[0].id'
    return 0
  fi

  echo "⚠️  Multiple iOS destinations found. Choose one:" >&2
  local i=0 line
  while IFS= read -r line; do
    i=$((i + 1))
    echo "   $i) $line" >&2
  done < <(echo "$ios_devices" | jq -r '.[] | "\(.name) (\(.id))"')

  # Never block on read without a TTY, or a non-interactive run (CI, nested
  # automation) hangs indefinitely instead of failing with a usable message.
  if [[ ! -t 0 ]]; then
    echo "   ❌ No terminal available to choose a device." >&2
    echo "      Disconnect the extras, or boot only the simulator you want, and re-run." >&2
    return 1
  fi

  local choice
  read -rp "   Enter number [1-${count}]: " choice
  if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "$count" ]; then
    echo "$ios_devices" | jq -r ".[$((choice - 1))].id"
    return 0
  fi
  echo "❌ Invalid selection." >&2
  return 1
}

# #########
# Build iOS
# #########
function run_build_ios() {
  local flavor="${1:-dev}"
  shift || true
  check_ios_prerequisites || return 1
  local device_id
  device_id=$(select_ios_device) || return 1
  flutter pub get \
    && pushd ios && pod install --repo-update && popd \
    && dart run build_runner build \
    && flutter run --flavor "$flavor" -d "$device_id" "$@"
}


if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
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
fi
