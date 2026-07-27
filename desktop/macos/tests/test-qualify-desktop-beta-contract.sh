#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUALIFIER="$SCRIPT_DIR/../scripts/qualify-desktop-beta.sh"
CORE_HARNESS="$SCRIPT_DIR/../scripts/desktop-core-harness.sh"
PROFILE_PREP="$SCRIPT_DIR/../scripts/prepare-qualification-profile.sh"
SWIFT_CACHE="$SCRIPT_DIR/../scripts/qualification-swift-cache.sh"
LEASE_COMMAND="$SCRIPT_DIR/../scripts/qualification-lease-command.sh"
APP_CONFIG="$SCRIPT_DIR/../scripts/app-config.sh"
RUN_SH="$SCRIPT_DIR/../run.sh"
WORKFLOW="$SCRIPT_DIR/../../../.github/workflows/desktop_qualify_beta.yml"

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
# omi-test-quality: source-inspection -- static contract: detached qualification
# launches must persist token-bound provenance and can never fall back to broad
# bundle-id/app-name termination; an isolated live macOS launcher is not portable.
require_text 'OMI_DESKTOP_LAUNCH_TOKEN="$DESKTOP_LAUNCH_TOKEN"'
require_text 'secrets.token_urlsafe(24)'
require_text 'record_owned_qualification_desktop'
require_text 'validated_qualification_desktop_pid'
require_text 'stop_recorded_qualification_desktop'
require_text 'stat.S_IMODE(signal.stat().st_mode) != 0o600'
require_text 'target.chmod(0o600)'
require_text 'command_sha256'
require_text 'lsof -nP -iTCP:"$AUTOMATION_PORT" -sTCP:LISTEN'
require_text 'qualification automation port remains bound after owned app cleanup'
require_text 'kill -KILL "$pid"'
require_text 'refusing unproven qualification app cleanup'
require_text 'cleanup failed; preserving qualification lease and preventing success evidence'
if grep -Eq 'osascript|pkill|kill_process_tree|quit app id' "$QUALIFIER"; then
  echo "FAIL: qualification cleanup must not use broad app-name or bundle-id termination" >&2
  exit 1
fi
require_order "$QUALIFIER" \
  'if ! record_owned_qualification_desktop; then' \
  './scripts/desktop-core-harness.sh --tier 2' \
  'if ! run_qualification_cleanup; then' \
  'if [[ "$GITHUB_ACTIONS_ARTIFACT" -eq 1 ]]'
require_text 'terminate_qualification_desktop "$BUNDLE"'
require_text '--json tagName,isDraft,isPrerelease,publishedAt,assets,body'
require_text '"$SCRIPT_DIR/qualification-swift-cache.sh" prepare'
require_text 'QUALIFICATION_CACHE_LEASE_ID'
require_text 'QUALIFICATION_CACHE_LEASE_TOKEN'
require_text '"$SCRIPT_DIR/qualification-swift-cache.sh" release'
require_text 'qualification-cache-reclaim.py' "$SWIFT_CACHE"
require_text 'qualification-lease "$action"' "$LEASE_COMMAND"
require_text 'acquire)' "$LEASE_COMMAND"
require_text 'preflight-fault-cleanup)' "$LEASE_COMMAND"
require_text 'release)' "$LEASE_COMMAND"
require_text 'qualification-lease-command.sh' "$QUALIFIER"
require_text 'OMI_HARNESS_PORT_OFFSET="$QUALIFICATION_PORT_OFFSET"'
require_text 'OMI_AUTOMATION_PORT="$((47777 + QUALIFICATION_PORT_OFFSET))"'
require_text 'QUALIFICATION_RETAINED_RUNS="${OMI_QUALIFICATION_RETAINED_RUNS:-3}"'
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
require_text 'python3 "$KEYVALUE_PY" check-fault-manifest "$FAULT_EVIDENCE/manifest.json"'
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

# Runner-only listener cleanup must prove its exact token/PID/port lineage before
# the expensive app build or any user-flow suite. Unknown listeners still fail
# closed, and phase timings make the 20-minute target measurable without
# weakening artifact, Tier-2, or fault evidence.
require_order "$QUALIFIER" \
  'phase_begin "fault-listener-preflight" "runner-hygiene-cleanup"' \
  '"$LEASE_COMMAND" preflight-fault-cleanup' \
  'phase_begin "desktop-preparation" "runner-hygiene-cleanup"' \
  'phase_begin "tier-2-user-flows" "user-visible-behavioral-fault"' \
  'phase_begin "fault-user-flow" "user-visible-behavioral-fault"' \
  'phase_begin "final-cleanup" "runner-hygiene-cleanup"'
require_text '"target_seconds": 1200'
require_text 'OMI_QUALIFICATION_TIMINGS_FILE' "$QUALIFIER"
require_text 'OMI_QUALIFICATION_FAULT_PREFLIGHT_REPORT' "$QUALIFIER"
require_text '/phase-timings.json' "$SCRIPT_DIR/../../../.github/workflows/desktop_qualify_beta.yml"
require_text '/fault-listener-preflight.json' "$SCRIPT_DIR/../../../.github/workflows/desktop_qualify_beta.yml"

# The canonical qualification owns the only M1 qualification lease lifecycle.
# Its ordered preflight/final cleanup is retained as artifact evidence; no
# standalone local-proof job may create an earlier duplicate lease.
if grep -Fq 'local-proof-m1' "$WORKFLOW" || grep -Fq 'qualification-local-proof.sh' "$WORKFLOW"; then
  echo "FAIL: qualification workflow must not retain a duplicate local-proof lifecycle" >&2
  exit 1
fi
require_order "$WORKFLOW" \
  'qualify-m1-studio:' \
  'fault-listener-preflight.json' \
  'phase-timings.json'

if [[ ! -x "$PROFILE_PREP" ]]; then
  echo "FAIL: missing executable qualification profile preparation helper" >&2
  exit 1
fi
if [[ ! -x "$SWIFT_CACHE" ]]; then
  echo "FAIL: missing executable exact-source qualification Swift cache helper" >&2
  exit 1
fi
if [[ ! -x "$LEASE_COMMAND" ]]; then
  echo "FAIL: missing executable qualification lease command helper" >&2
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
