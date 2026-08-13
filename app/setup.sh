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

  # 3. Fallback: offer the teams named by installed profiles, but only if this
  #    machine holds an iOS development identity at all.
  #
  #    Deliberately does NOT try to decide which team a certificate belongs to.
  #    The team in a certificate's common name is not authoritative: Apple keeps
  #    the original personal-team ID there when a developer joins a paid team, so
  #    a certificate reading "Apple Development: NAME (PERSONALTEAM)" can be
  #    issued under a different team entirely — the real one is the OU, readable
  #    only by decoding the certificate. Matching the common name therefore
  #    rejects teams the developer can sign for and accepts ones they cannot.
  #
  #    The profile's own TeamIdentifier is authoritative, so that is what gets
  #    offered. The identity check is a presence test only: with no iOS
  #    development identity, nothing here is signable and prompting for a team
  #    would be pointless. "iPhone Developer" is the legacy name for the same
  #    identity and still exists on older machines. "Developer ID Application"
  #    is deliberately excluded — it signs Mac distribution builds and cannot
  #    sign an iOS development build.
  #
  #    When several teams qualify this cannot tell them apart, so it asks rather
  #    than guessing — see the prompt below.
  # SHA-1 fingerprints of the iOS development identities whose private keys this
  # machine holds. "Developer ID Application" is excluded: it signs Mac
  # distribution builds and cannot sign an iOS development build.
  local held_fingerprints
  held_fingerprints=$(security find-identity -v -p codesigning 2>/dev/null \
    | grep -E "Apple Development|iPhone Developer" \
    | awk '{print toupper($2)}' | grep -E '^[0-9A-F]{40}$')

  if [ -z "$team_id" ] && [ -d "$profiles_dir" ] && [ -n "$held_fingerprints" ]; then
    local seen_teams=()
    while IFS= read -r -d '' profile; do
      local plist candidate
      plist=$(security cms -D -i "$profile" 2>/dev/null) || continue
      candidate=$(echo "$plist" | xmllint --xpath \
        "string(//key[text()='TeamIdentifier']/following-sibling::array[1]/string[1])" \
        - 2>/dev/null)
      [ -n "$candidate" ] || continue

      local already_seen=false
      for t in "${seen_teams[@]:-}"; do [ "$t" = "$candidate" ] && already_seen=true && break; done
      $already_seen && continue

      # Offer the team only if the profile embeds a certificate whose private key
      # is on this machine — the same question Xcode asks when it picks a profile.
      # Deliberately not decided from the certificate's common name: Apple keeps
      # the original personal-team ID there when a developer joins a paid team, so
      # a certificate reading "Apple Development: NAME (PERSONALTEAM)" can be
      # issued under a different team (the real one is the OU). Matching the name
      # both rejects teams the developer can sign for and accepts ones they cannot.
      local usable=false idx=0 der fingerprint
      while [ "$idx" -lt 50 ]; do
        der=$(printf '%s' "$plist" \
          | plutil -extract "DeveloperCertificates.$idx" raw -o - - 2>/dev/null) || break
        [ -n "$der" ] || break
        fingerprint=$(printf '%s' "$der" | base64 -d 2>/dev/null \
          | openssl x509 -inform DER -noout -fingerprint -sha1 2>/dev/null \
          | sed 's/.*=//; s/://g' | tr '[:lower:]' '[:upper:]')
        if [ -n "$fingerprint" ] && printf '%s\n' "$held_fingerprints" | grep -qx "$fingerprint"; then
          usable=true
          break
        fi
        idx=$((idx + 1))
      done
      $usable && seen_teams+=("$candidate")
    done < <(find "$profiles_dir" -name '*.mobileprovision' -print0 2>/dev/null)

    if [ "${#seen_teams[@]}" -eq 1 ]; then
      team_id="${seen_teams[0]}"
    elif [ "${#seen_teams[@]}" -gt 1 ]; then
      echo "⚠️  Multiple Apple Developer accounts found. Choose one:" >&2
      for i in "${!seen_teams[@]}"; do
        echo "   $((i+1))) ${seen_teams[$i]}" >&2
      done
      # Same reasoning as the prompt below: never block on read without a TTY.
      if [ -t 0 ]; then
        local choice
        read -rp "   Enter number [1-${#seen_teams[@]}]: " choice
        if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "${#seen_teams[@]}" ]; then
          team_id="${seen_teams[$((choice-1))]}"
        fi
      fi
    fi
  fi

  # 4. Last resort: prompt the user (with format validation)
  if [ -z "$team_id" ]; then
    echo "⚠️  Could not auto-detect your Apple Development Team ID." >&2
    echo "   Find it at: https://developer.apple.com/account -> Membership" >&2
    echo "   or run: APPLE_DEVELOPMENT_TEAM=XXXXXXXXXX bash setup.sh ios" >&2
    # Only prompt when a human is actually attached. Without this, a
    # non-interactive run (CI, nested automation) blocks forever on read
    # instead of failing with a usable message.
    if [ ! -t 0 ]; then
      echo "   ❌ No terminal available to prompt for a Team ID." >&2
      echo "      Set APPLE_DEVELOPMENT_TEAM and re-run." >&2
      return 1
    fi
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
    # The widget shares defaults through this group, so it must track the suffixed
    # bundle. Prod/beta inherit the unsuffixed default from Base.xcconfig.
    echo "APP_GROUP_IDENTIFIER=group.com.friend-app-with-wearable.ios12-${suffix}" >> ios/Flutter/Custom.xcconfig
  else
    # Beta uses a distinct bundle/callback identity and must be provisioned
    # explicitly by the developer's Apple team.
    echo "APP_BUNDLE_IDENTIFIER=${OMI_MOBILE_BETA_BUNDLE_ID:-com.friend-app-with-wearable.ios12.beta}" >> ios/Flutter/Custom.xcconfig
    echo "AUTH_CALLBACK_SCHEME=${callback_scheme}" >> ios/Flutter/Custom.xcconfig
  fi

  # Detect and write the Development Team ID so automatic signing resolves to the
  # developer's own Apple team rather than a hardcoded one.
  echo "🔍 Detecting Apple Development Team ID..."
  local development_team
  development_team=$(detect_apple_team_id)
  echo "✅ Team ID: ${development_team}"
  echo "DEVELOPMENT_TEAM=${development_team}" >> ios/Flutter/Custom.xcconfig
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
