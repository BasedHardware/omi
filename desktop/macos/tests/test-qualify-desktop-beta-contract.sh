#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUALIFIER="$SCRIPT_DIR/../scripts/qualify-desktop-beta.sh"
CORE_HARNESS="$SCRIPT_DIR/../scripts/desktop-core-harness.sh"
APP_CONFIG="$SCRIPT_DIR/../scripts/app-config.sh"

require_text() {
  local pattern="$1"
  local file="${2:-$QUALIFIER}"
  grep -Fq "$pattern" "$file" || {
    echo "FAIL: qualification bootstrap missing: $pattern" >&2
    exit 1
  }
}

require_text 'defaults delete "$bundle_id"'
require_text 'omi-qualification-*'
require_text 'Application Support/$bundle_name'
require_text 'defaults write "$bundle_id" hasCompletedOnboarding -bool true'
require_text 'defaults write "$bundle_id" devLazyPermissionsEnabled -bool true'
require_text 'defaults write "$bundle_id" screenAnalysisEnabled -bool false'
require_text 'defaults write "$bundle_id" transcriptionEnabled -bool false'
require_text 'OMI_SKIP_SETTINGS_SEED=1 make desktop-run-local'
require_text 'terminate_qualification_desktop "$BUNDLE"'
require_text 'derive_omi_app_config "$BUNDLE"' "$CORE_HARNESS"
require_text 'wrong bundle on port' "$CORE_HARNESS"

# Release qualification names contain SemVer punctuation; the preflight must
# compare against the same slugged identity run.sh installs.
source "$APP_CONFIG"
derive_omi_app_config 'omi-qualification-0.12.69+12069'
if [[ "$BUNDLE_ID" != 'com.omi.omi-qualification-0-12-69-12069' ]]; then
  echo "FAIL: qualification bundle ID was not canonically slugged: $BUNDLE_ID" >&2
  exit 1
fi

echo "desktop beta qualification bootstrap contract tests passed"
