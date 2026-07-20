#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUALIFIER="$SCRIPT_DIR/../scripts/qualify-desktop-beta.sh"
CORE_HARNESS="$SCRIPT_DIR/../scripts/desktop-core-harness.sh"
PROFILE_PREP="$SCRIPT_DIR/../scripts/prepare-qualification-profile.sh"
APP_CONFIG="$SCRIPT_DIR/../scripts/app-config.sh"

require_text() {
  local pattern="$1"
  local file="${2:-$QUALIFIER}"
  grep -Fq "$pattern" "$file" || {
    echo "FAIL: qualification bootstrap missing: $pattern" >&2
    exit 1
  }
}

require_text 'defaults delete "$BUNDLE_ID"' "$PROFILE_PREP"
require_text '^omi-qualification-' "$PROFILE_PREP"
require_text 'Application Support/$BUNDLE_NAME' "$PROFILE_PREP"
require_text 'defaults write "$BUNDLE_ID" hasCompletedOnboarding -bool true' "$PROFILE_PREP"
require_text 'defaults write "$BUNDLE_ID" devLazyPermissionsEnabled -bool true' "$PROFILE_PREP"
require_text 'defaults write "$BUNDLE_ID" screenAnalysisEnabled -bool false' "$PROFILE_PREP"
require_text 'defaults write "$BUNDLE_ID" transcriptionEnabled -bool false' "$PROFILE_PREP"
require_text '"$SCRIPT_DIR/prepare-qualification-profile.sh" "$BUNDLE"' "$QUALIFIER"
require_text 'OMI_SKIP_SETTINGS_SEED=1 make desktop-run-local'
require_text 'terminate_qualification_desktop "$BUNDLE"'
require_text 'derive_omi_app_config "$BUNDLE"' "$CORE_HARNESS"
require_text 'wrong bundle on port' "$CORE_HARNESS"

if [[ ! -x "$PROFILE_PREP" ]]; then
  echo "FAIL: missing executable qualification profile preparation helper" >&2
  exit 1
fi

# Profile preparation is shared by release qualification and direct local retries.
# Exercise it with an isolated preferences home so this contract never reads or
# changes a developer's real qualification profile.
prefs_home="$(mktemp -d "${TMPDIR:-/tmp}/omi-qualification-profile.XXXXXX")"
trap 'rm -rf "$prefs_home"' EXIT
bundle_name="omi-qualification-contract-$$"
source "$APP_CONFIG"
derive_omi_app_config "$bundle_name"
HOME="$prefs_home" "$PROFILE_PREP" "$bundle_name"
if [[ "$(HOME="$prefs_home" defaults read "$BUNDLE_ID" hasCompletedOnboarding)" != "1" ]]; then
  echo "FAIL: prepared qualification profile must complete onboarding" >&2
  exit 1
fi
if [[ "$(HOME="$prefs_home" defaults read "$BUNDLE_ID" devLazyPermissionsEnabled)" != "1" ]]; then
  echo "FAIL: prepared qualification profile must enable lazy dev permissions" >&2
  exit 1
fi
if HOME="$prefs_home" "$PROFILE_PREP" 'omi-not-a-qualification' >/dev/null 2>&1; then
  echo "FAIL: profile preparation accepted a non-qualification bundle" >&2
  exit 1
fi

# Release qualification names contain SemVer punctuation; the preflight must
# compare against the same slugged identity run.sh installs.
source "$APP_CONFIG"
derive_omi_app_config 'omi-qualification-0.12.69+12069'
if [[ "$BUNDLE_ID" != 'com.omi.omi-qualification-0-12-69-12069' ]]; then
  echo "FAIL: qualification bundle ID was not canonically slugged: $BUNDLE_ID" >&2
  exit 1
fi

echo "desktop beta qualification bootstrap contract tests passed"
