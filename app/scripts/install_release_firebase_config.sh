#!/usr/bin/env bash
set -euo pipefail

# Install the committed Firebase client config that release builds compile against.
#
# Codemagic used to regenerate these files on every build with
# `flutterfire config --service-account=<firebase-adminsdk JSON key>`, which kept a
# production Owner service-account key in Codemagic only to download public client
# config. The outputs are committed in setup/release-firebase/ instead (they are the
# same non-secret identifiers every shipped APK/IPA already carries), so a build needs
# no Google Cloud credential.
#
# To refresh after a Firebase app changes, run the two `flutterfire config` commands in
# setup/release-firebase/README.md with your own login (never a key), copy the outputs
# back into setup/release-firebase/, and review the diff.
#
# Usage: scripts/install_release_firebase_config.sh [app-dir]

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$APP_DIR/setup/release-firebase"
DEST_DIR="${1:-$APP_DIR}"

install_file() {
  local source="$SRC_DIR/$1"
  local target="$DEST_DIR/$2"
  [[ -f "$source" ]] || { echo "missing committed Firebase config: $source" >&2; exit 1; }
  mkdir -p "$(dirname "$target")"
  cp "$source" "$target"
}

require_project() {
  local file="$DEST_DIR/$1"
  local project="$2"
  grep -q -- "$project" "$file" || {
    echo "$1 does not name Firebase project $project" >&2
    exit 1
  }
}

install_file firebase_options_prod.dart lib/firebase_options_prod.dart
install_file firebase_options_dev.dart lib/firebase_options_dev.dart
install_file google-services.prod.json android/app/src/prod/google-services.json
install_file google-services.dev.json android/app/src/dev/google-services.json
install_file GoogleService-Info.prod.plist ios/Config/Prod/GoogleService-Info.plist
install_file GoogleService-Info.dev.plist ios/Config/Dev/GoogleService-Info.plist

require_project lib/firebase_options_prod.dart "projectId: 'based-hardware',"
require_project lib/firebase_options_dev.dart "projectId: 'based-hardware-dev',"
require_project android/app/src/prod/google-services.json '"project_id": "based-hardware",'
require_project android/app/src/dev/google-services.json '"project_id": "based-hardware-dev",'
require_project ios/Config/Prod/GoogleService-Info.plist '<string>based-hardware</string>'
require_project ios/Config/Dev/GoogleService-Info.plist '<string>based-hardware-dev</string>'

echo "Installed committed Firebase client config (prod: based-hardware, dev: based-hardware-dev)."
