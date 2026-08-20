#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_defaults() {
  local domain="$1" key="$2" expected="$3"
  local actual
  actual="$(defaults read "$domain" "$key")"
  if [ "$actual" != "$expected" ]; then
    fail "$domain $key: expected '$expected', got '$actual'"
  fi
}

assert_unset() {
  local domain="$1" key="$2"
  if defaults read "$domain" "$key" >/dev/null 2>&1; then
    fail "$domain $key: expected unset"
  fi
}

cleanup_domains=()
prefs_home="$(mktemp -d "${TMPDIR:-/tmp}/omi-settings-seed-home.XXXXXX")"
mkdir -p "$prefs_home/Library/Preferences"
export HOME="$prefs_home"
export CFFIXED_USER_HOME="$prefs_home"
cleanup() {
  for domain in "${cleanup_domains[@]}"; do
    defaults delete "$domain" >/dev/null 2>&1 || true
  done
  rm -rf "$prefs_home"
}
trap cleanup EXIT

source_domain="com.omi.codex-settings-source-$$"
quiet_target="com.omi.codex-settings-quiet-$$"
eager_target="com.omi.codex-settings-eager-$$"
missing_target="com.omi.codex-settings-missing-$$"
empty_source="com.omi.codex-settings-empty-$$"
empty_target="com.omi.codex-settings-empty-target-$$"
cleanup_domains+=("$source_domain" "$quiet_target" "$eager_target" "$missing_target" "$empty_source" "$empty_target")

defaults write "$source_domain" screenAnalysisEnabled -bool true
defaults write "$source_domain" transcriptionEnabled -bool true
defaults write "$source_domain" systemAudioCaptureMode -string onlyDuringMeetings
defaults write "$source_domain" shortcut_askOmiEnabled -bool true
# Persist exact shortcut payloads, matching ShortcutSettings' Data-backed JSON.
defaults write "$source_domain" shortcut_askOmiKey -data 7b226b6579446973706c6179223a224a222c226b6579436f6465223a33382c226d6f6469666965727352617756616c7565223a313034383537362c226d6f6469666965724f6e6c79223a66616c73652c2272657175697265735269676874436f6d6d616e64223a66616c73657d
defaults write "$source_domain" shortcut_pttKey -data 7b226b6579446973706c6179223a2255222c226b6579436f6465223a33322c226d6f6469666965727352617756616c7565223a3532343238382c226d6f6469666965724f6e6c79223a66616c73652c2272657175697265735269676874436f6d6d616e64223a66616c73657d
# Set the hidden kill switch in the source to verify it is NOT copied to targets.
defaults write "$source_domain" disableSystemAudioCapture -bool true

# Stale values prove the helper replaces both hotkeys instead of merely filling
# an empty target domain.
defaults write "$quiet_target" shortcut_askOmiKey -data 7374616c652d61736b
defaults write "$quiet_target" shortcut_pttKey -data 7374616c652d707474

"$MACOS_DIR/scripts/omi-settings-seed.sh" "$quiet_target" "$source_domain" >"$prefs_home/omi-settings-seed-quiet.out"
assert_defaults "$quiet_target" screenAnalysisEnabled 1
assert_defaults "$quiet_target" audioRecordingMode off
assert_unset "$quiet_target" transcriptionEnabled
assert_unset "$quiet_target" systemAudioCaptureMode
assert_defaults "$quiet_target" devLazyPermissionsEnabled 1
assert_unset "$quiet_target" screenAnalysisAutoStartFixed_v2
assert_unset "$quiet_target" screenAnalysisAutoStartFixed_v3
assert_unset "$quiet_target" disableSystemAudioCapture
assert_defaults "$quiet_target" shortcut_askOmiEnabled 1
assert_unset "$quiet_target" hasCompletedFileIndexing
python3 - "$source_domain" "$quiet_target" <<'PY'
import json
import plistlib
import subprocess
import sys


def export(domain):
    proc = subprocess.run(["defaults", "export", domain, "-"], capture_output=True, check=True)
    return plistlib.loads(proc.stdout)


source, target = map(export, sys.argv[1:])
for key in ("shortcut_askOmiKey", "shortcut_pttKey"):
    if target.get(key) != source.get(key):
        raise SystemExit(f"{key} did not mirror the source payload")
    decoded = json.loads(source[key])
    required = {"keyDisplay", "keyCode", "modifiersRawValue", "modifierOnly", "requiresRightCommand"}
    if set(decoded) != required:
        raise SystemExit(f"{key} is not a valid ShortcutSettings payload: {sorted(decoded)}")
PY

# Removing a source override must remove the target override too, otherwise the
# two bundles fall back to different compiled defaults after a Swift-only build.
defaults delete "$source_domain" shortcut_pttKey
"$MACOS_DIR/scripts/omi-settings-seed.sh" "$quiet_target" "$source_domain" >/dev/null
assert_unset "$quiet_target" shortcut_pttKey

# A successful empty source export is still an existing source domain. Its
# absent shortcut keys must clear stale target overrides instead of being
# treated as an unreadable/missing source.
defaults write "$empty_source" temporaryMarker -bool true
defaults delete "$empty_source" temporaryMarker
defaults write "$empty_target" shortcut_askOmiKey -data 7374616c652d61736b
defaults write "$empty_target" shortcut_pttKey -data 7374616c652d707474
"$MACOS_DIR/scripts/omi-settings-seed.sh" "$empty_target" "$empty_source" >/dev/null
assert_unset "$empty_target" shortcut_askOmiKey
assert_unset "$empty_target" shortcut_pttKey

OMI_DEV_EAGER_PERMISSIONS=1 "$MACOS_DIR/scripts/omi-settings-seed.sh" "$eager_target" "$source_domain" >"$prefs_home/omi-settings-seed-eager.out"
assert_defaults "$eager_target" screenAnalysisEnabled 1
assert_defaults "$eager_target" audioRecordingMode onlyMeetings
assert_defaults "$eager_target" devLazyPermissionsEnabled 0
assert_unset "$eager_target" disableSystemAudioCapture
assert_unset "$eager_target" transcriptionEnabled
assert_unset "$eager_target" systemAudioCaptureMode
assert_unset "$eager_target" screenAnalysisAutoStartFixed_v2
assert_unset "$eager_target" screenAnalysisAutoStartFixed_v3

# A genuinely missing source preserves ordinary target preferences but still
# applies the intentional target-only quiet-permission safety policy.
defaults write "$missing_target" fontScale -float 1.75
defaults write "$missing_target" shortcut_askOmiKey -data 70726573657276652d61736b
defaults write "$missing_target" disableSystemAudioCapture -bool true
defaults write "$missing_target" screenAnalysisAutoStartFixed_v2 -bool true
"$MACOS_DIR/scripts/omi-settings-seed.sh" "$missing_target" "com.omi.missing-source-$$" >"$prefs_home/omi-settings-seed-missing.out"
assert_defaults "$missing_target" screenAnalysisEnabled 1
assert_defaults "$missing_target" audioRecordingMode off
assert_defaults "$missing_target" devLazyPermissionsEnabled 1
assert_defaults "$missing_target" fontScale 1.75
python3 - "$missing_target" <<'PY'
import plistlib
import subprocess
import sys

proc = subprocess.run(["defaults", "export", sys.argv[1], "-"], capture_output=True, check=True)
if plistlib.loads(proc.stdout).get("shortcut_askOmiKey") != b"preserve-ask":
    raise SystemExit("missing source must preserve the target shortcut override")
PY
assert_unset "$missing_target" disableSystemAudioCapture
assert_unset "$missing_target" screenAnalysisAutoStartFixed_v2

# Verify eager mode fully undoes quiet defaults when re-seeding the same target.
# Seed quiet first, then eager on the same target without source capture flags.
quiet_then_eager_target="com.omi.codex-settings-qe-$$"
cleanup_domains+=("$quiet_then_eager_target")
"$MACOS_DIR/scripts/omi-settings-seed.sh" "$quiet_then_eager_target" "$source_domain" >/dev/null
# Source without capture flags to verify eager defaults kick in.
bare_source="com.omi.codex-settings-bare-$$"
cleanup_domains+=("$bare_source")
defaults write "$bare_source" shortcut_askOmiEnabled -bool true
OMI_DEV_EAGER_PERMISSIONS=1 "$MACOS_DIR/scripts/omi-settings-seed.sh" "$quiet_then_eager_target" "$bare_source" >/dev/null
assert_defaults "$quiet_then_eager_target" screenAnalysisEnabled 1
assert_defaults "$quiet_then_eager_target" audioRecordingMode onlyMeetings
assert_defaults "$quiet_then_eager_target" devLazyPermissionsEnabled 0
assert_unset "$quiet_then_eager_target" transcriptionEnabled
assert_unset "$quiet_then_eager_target" systemAudioCaptureMode
assert_unset "$quiet_then_eager_target" disableSystemAudioCapture
assert_unset "$quiet_then_eager_target" screenAnalysisAutoStartFixed_v2
assert_unset "$quiet_then_eager_target" screenAnalysisAutoStartFixed_v3

# omi-test-quality: source-inspection -- static contract: named-bundle settings seeding stays on the common prelaunch path shared by fast and full bundle builds.
python3 - "$MACOS_DIR/run.sh" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
seed_call = './scripts/omi-settings-seed.sh "$BUNDLE_ID" com.omi.desktop-dev'
if source.count(seed_call) != 1:
    raise SystemExit("run.sh must have exactly one named-bundle settings seed call")
fast = source.index('if [ "$FAST_BUNDLE" = "1" ]; then')
common = source.index("fi # full bundle path", fast)
seed = source.index(seed_call)
launch = source.index('step "Starting app..."')
if not fast < common < seed < launch:
    raise SystemExit("settings seed must run on the common path after fast/full converge and before launch")
seed_block = source[seed:launch]
if "exit 1" not in seed_block or "OMI_SKIP_SETTINGS_SEED=1" not in seed_block:
    raise SystemExit("settings seed failure must stop launch and name the explicit bundle-local escape hatch")
PY

echo "settings-seed tests passed"
