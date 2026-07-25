#!/usr/bin/env bash
# Prepare the isolated local state used by a named desktop qualification bundle.
#
# This is intentionally reusable: release qualification and direct local retry
# lanes must start from the same signed-in, onboarded synthetic-profile defaults.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_NAME="${1:-}"

if [[ ! "$BUNDLE_NAME" =~ ^omi-qualification-[A-Za-z0-9.+-]+$ ]]; then
  echo "refusing to prepare non-qualification profile: ${BUNDLE_NAME:-<empty>}" >&2
  exit 2
fi

# shellcheck source=app-config.sh
source "$SCRIPT_DIR/app-config.sh"
derive_omi_app_config "$BUNDLE_NAME"

# Qualification profiles never inherit onboarding, capture, shortcut, or UI
# state from a previous attempt or from Omi Dev.
rm -rf "$HOME/Library/Application Support/$BUNDLE_NAME" "$HOME/Library/Caches/$BUNDLE_NAME"
defaults delete "$BUNDLE_ID" >/dev/null 2>&1 || true
defaults write "$BUNDLE_ID" hasCompletedOnboarding -bool true
defaults write "$BUNDLE_ID" devLazyPermissionsEnabled -bool true
defaults write "$BUNDLE_ID" screenAnalysisEnabled -bool false
defaults write "$BUNDLE_ID" transcriptionEnabled -bool false
defaults write "$BUNDLE_ID" systemAudioCaptureMode -string never
defaults write "$BUNDLE_ID" screenAnalysisAutoStartFixed_v2 -bool true
defaults write "$BUNDLE_ID" shortcut_floatingBarTypedQuestionVoiceAnswersEnabled -bool false

echo "prepared qualification profile: $BUNDLE_NAME ($BUNDLE_ID)"
