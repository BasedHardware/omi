#!/bin/bash
#
# Personal build config overlay — run after setup.sh.
#
# Copies personal Firebase credentials and dev environment config from
# .personal_configs/ at the repo root into the app for local dev builds.
#
# Usage:
#   bash setup-personal.sh [ngrok-url]
#
#   ngrok-url  Optional. Overrides API_BASE_URL in .dev.env.
#              e.g. https://xyz.ngrok-free.dev/
#              If omitted, uses the API_BASE_URL from .personal_configs/.dev.env.
#
# Setup:
#   1. Copy .personal_configs.example/ to .personal_configs/ at the repo root.
#   2. cp .personal_configs/.dev.env.template .personal_configs/.dev.env
#      then fill in your API keys and backend URL.
#   3. Add your GoogleService-Info.plist and firebase_options_dev.dart.
#   4. Run this script from anywhere inside the repo.
#
# .personal_configs/ is gitignored — its contents are never committed.

set -euo pipefail

# Resolve paths relative to this script, regardless of where it's called from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_DIR="${REPO_ROOT}/.personal_configs"

cd "$SCRIPT_DIR"

if [ ! -d "$CONFIG_DIR" ]; then
  echo "Error: .personal_configs/ not found at ${REPO_ROOT}" >&2
  echo "" >&2
  echo "To set up:" >&2
  echo "  cp -r ${REPO_ROOT}/.personal_configs.example ${CONFIG_DIR}" >&2
  echo "  cp ${CONFIG_DIR}/.dev.env.template ${CONFIG_DIR}/.dev.env" >&2
  echo "  # then fill in .dev.env and add your Firebase credential files" >&2
  exit 1
fi

# --- GoogleService-Info.plist ---
PLIST="${CONFIG_DIR}/GoogleService-Info.plist"
if [ ! -f "$PLIST" ]; then
  echo "Error: ${PLIST} not found" >&2
  exit 1
fi

mkdir -p ios/Config/Dev ios/Runner
cp "$PLIST" ios/Config/Dev/GoogleService-Info.plist
cp "$PLIST" ios/Runner/GoogleService-Info.plist
echo "✓ Copied GoogleService-Info.plist → ios/Config/Dev/ and ios/Runner/"

# --- firebase_options_dev.dart ---
FIREBASE_OPTS="${CONFIG_DIR}/firebase_options_dev.dart"
if [ ! -f "$FIREBASE_OPTS" ]; then
  echo "Error: ${FIREBASE_OPTS} not found" >&2
  exit 1
fi

mkdir -p lib
cp "$FIREBASE_OPTS" lib/firebase_options_dev.dart
echo "✓ Copied firebase_options_dev.dart → lib/"

# --- .dev.env ---
DEV_ENV="${CONFIG_DIR}/.dev.env"
if [ ! -f "$DEV_ENV" ]; then
  echo "Error: ${DEV_ENV} not found" >&2
  echo "  cp ${CONFIG_DIR}/.dev.env.template ${DEV_ENV} and fill it in" >&2
  exit 1
fi

# If a URL was passed as $1, override API_BASE_URL; otherwise copy .dev.env as-is.
if [ $# -ge 1 ]; then
  NGROK_URL="$1"
  [[ "$NGROK_URL" != */ ]] && NGROK_URL="${NGROK_URL}/"
  # Copy the template then override API_BASE_URL
  cp "$DEV_ENV" .dev.env
  if grep -q '^API_BASE_URL=' .dev.env; then
    sed -i '' "s|^API_BASE_URL=.*|API_BASE_URL=${NGROK_URL}|" .dev.env
  else
    echo "API_BASE_URL=${NGROK_URL}" >> .dev.env
  fi
  echo "✓ Wrote .dev.env (API_BASE_URL overridden to ${NGROK_URL})"
else
  cp "$DEV_ENV" .dev.env
  echo "✓ Copied .dev.env from .personal_configs/"
fi

echo ""
echo "Personal config applied. Run 'flutter pub run build_runner build' to regenerate env files."
