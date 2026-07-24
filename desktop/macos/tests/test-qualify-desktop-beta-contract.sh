#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUALIFIER="$SCRIPT_DIR/../scripts/qualify-desktop-beta.sh"
CORE_HARNESS="$SCRIPT_DIR/../scripts/desktop-core-harness.sh"
PROFILE_PREP="$SCRIPT_DIR/../scripts/prepare-qualification-profile.sh"
SWIFT_CACHE="$SCRIPT_DIR/../scripts/qualification-swift-cache.sh"
APP_CONFIG="$SCRIPT_DIR/../scripts/app-config.sh"
RUN_SH="$SCRIPT_DIR/../run.sh"

require_text() {
  local pattern="$1"
  local file="${2:-$QUALIFIER}"
  grep -Fq -- "$pattern" "$file" || {
    echo "FAIL: qualification bootstrap missing: $pattern" >&2
    exit 1
  }
}

require_order() {
  local file="$1"
  shift
  python3 - "$file" "$@" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
needles = sys.argv[2:]
text = path.read_text(encoding="utf-8")
position = -1
for needle in needles:
    next_position = text.find(needle, position + 1)
    if next_position < 0:
        raise SystemExit(f"FAIL: {path} missing ordered launch-phase fragment: {needle}")
    position = next_position
PY
}

require_text 'defaults delete "$BUNDLE_ID"' "$PROFILE_PREP"
require_text '^omi-qualification-' "$PROFILE_PREP"
require_text 'Application Support/$BUNDLE_NAME' "$PROFILE_PREP"
require_text 'defaults write "$BUNDLE_ID" hasCompletedOnboarding -bool true' "$PROFILE_PREP"
require_text 'defaults write "$BUNDLE_ID" devLazyPermissionsEnabled -bool true' "$PROFILE_PREP"
require_text 'defaults write "$BUNDLE_ID" screenAnalysisEnabled -bool false' "$PROFILE_PREP"
require_text 'defaults write "$BUNDLE_ID" transcriptionEnabled -bool false' "$PROFILE_PREP"
require_text '"$SCRIPT_DIR/prepare-qualification-profile.sh" "$BUNDLE"' "$QUALIFIER"
require_text 'OMI_SKIP_SETTINGS_SEED=1'
require_text 'make desktop-run-local DESKTOP_APP_NAME="$BUNDLE" DESKTOP_USER=alice'
require_text 'terminate_qualification_desktop "$BUNDLE"'
require_text '--json tagName,isDraft,isPrerelease,publishedAt,assets,body'
require_text 'WORKTREE="$("$SCRIPT_DIR/qualification-swift-cache.sh" prepare "$SHA" "$REPO_ROOT")"'
if grep -Fq 'worktree add' "$QUALIFIER" || grep -Fq 'rm -rf "$WORKTREE"' "$QUALIFIER"; then
  echo "FAIL: qualification must use the persistent exact-SHA source directly" >&2
  exit 1
fi
require_text "for-each-ref --count=1 --sort=-v:refname"
require_text "--format='%(refname:strip=2)' 'refs/tags/v*-macos'"

# Acceleration changes bootstrap only. The signed-artifact, static self-check,
# Tier-2, fault-suite, evidence, and newest-candidate gates remain mandatory.
require_text 'python3 "$KEYVALUE_PY" preflight-release'
require_text './scripts/desktop-core-harness.sh --self-check --skip-backend-contracts'
require_text './scripts/desktop-core-harness.sh --tier 2 --bundle "$BUNDLE" --port "$AUTOMATION_PORT" --keep-stack'
require_text 'python3 "$KEYVALUE_PY" check-manifest "$EVIDENCE/manifest.json"'
require_text './scripts/desktop-core-harness.sh --fault-suite --port "$((AUTOMATION_PORT + 1))"'
require_text 'manifest.get("passed") is not True or manifest.get("tier") != "fault"'
require_text 'evidence["automatic_gates"] = ["signed-artifact", "static-self-check", "tier-2", "fault-suite"]'
require_text 'if [[ "$LATEST_TAG" != "$RELEASE_TAG" ]]'
require_text 'python3 "$KEYVALUE_PY" update-qualified-beta'
require_text 'derive_omi_app_config "$BUNDLE"' "$CORE_HARNESS"
require_text 'wrong bundle on port' "$CORE_HARNESS"

# Static timing contract: cold preparation has its own bounded phase (env-
# overridable via OMI_QUALIFY_PREPARE_WAIT_SECS) and run.sh explicitly signals
# successful launch dispatch before the separate 900-second bridge readiness
# phase starts. Default preparation budget 5400s; combined bound 6300s.
# History: 1800s (compiling stalled at 1107/1182, run 29904736566) → 3600s,
# which STILL expired at 1139/1190 on a cold M1 self-hosted build (run
# 29965341760), timing out every fresh tag (v0.12.99–v0.12.113) and leaving no
# reusable .build for the warm retry. 5400s covers the observed ~75-min cold path.
require_text 'DESKTOP_PREPARE_WAIT_SECS="${OMI_QUALIFY_PREPARE_WAIT_SECS:-5400}"'
require_text 'BRIDGE_WAIT_SECS=900'
prepare_wait_secs="$(sed -n 's/.*OMI_QUALIFY_PREPARE_WAIT_SECS:-\([0-9]*\)}.*/\1/p' "$QUALIFIER")"
bridge_wait_secs="$(sed -n 's/^BRIDGE_WAIT_SECS=//p' "$QUALIFIER")"
if [[ "$prepare_wait_secs" -ne 5400 || "$bridge_wait_secs" -ne 900 \
  || $((prepare_wait_secs + bridge_wait_secs)) -ne 6300 ]]; then
  echo "FAIL: qualification timing bounds must remain 5400s preparation + 900s bridge = 6300s total" >&2
  exit 1
fi
require_text 'OMI_DESKTOP_LAUNCH_SIGNAL_FILE="$LAUNCH_SIGNAL_FILE"'
require_text 'signal_desktop_launch' "$RUN_SH"
require_order "$QUALIFIER" \
  'rm -f "$LAUNCH_SIGNAL_FILE"' \
  'DESKTOP_LAUNCH_PID=$!' \
  'wait_for_desktop_launch "$LAUNCH_SIGNAL_FILE"' \
  'SECONDS=0' \
  'wait_for_bridge "$AUTOMATION_PORT"'
require_order "$RUN_SH" \
  'step "Starting app..."' \
  'open "$APP_PATH"' \
  'signal_desktop_launch'

if [[ ! -x "$PROFILE_PREP" ]]; then
  echo "FAIL: missing executable qualification profile preparation helper" >&2
  exit 1
fi
if [[ ! -x "$SWIFT_CACHE" ]]; then
  echo "FAIL: missing executable exact-source qualification Swift cache helper" >&2
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
