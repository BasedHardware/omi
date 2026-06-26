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
cleanup() {
  for domain in "${cleanup_domains[@]}"; do
    defaults delete "$domain" >/dev/null 2>&1 || true
  done
}
trap cleanup EXIT

source_domain="com.omi.codex-settings-source-$$"
quiet_target="com.omi.codex-settings-quiet-$$"
eager_target="com.omi.codex-settings-eager-$$"
missing_target="com.omi.codex-settings-missing-$$"
cleanup_domains+=("$source_domain" "$quiet_target" "$eager_target" "$missing_target")

defaults write "$source_domain" screenAnalysisEnabled -bool true
defaults write "$source_domain" transcriptionEnabled -bool true
defaults write "$source_domain" shortcut_askOmiEnabled -bool true

"$MACOS_DIR/scripts/omi-settings-seed.sh" "$quiet_target" "$source_domain" >/tmp/omi-settings-seed-quiet.out
assert_defaults "$quiet_target" screenAnalysisEnabled 0
assert_defaults "$quiet_target" transcriptionEnabled 0
assert_defaults "$quiet_target" disableSystemAudioCapture 1
assert_defaults "$quiet_target" systemAudioCaptureMode never
assert_defaults "$quiet_target" devLazyPermissionsEnabled 1
assert_defaults "$quiet_target" screenAnalysisAutoStartFixed_v2 1
assert_defaults "$quiet_target" shortcut_askOmiEnabled 1
assert_unset "$quiet_target" hasCompletedFileIndexing

OMI_DEV_EAGER_PERMISSIONS=1 "$MACOS_DIR/scripts/omi-settings-seed.sh" "$eager_target" "$source_domain" >/tmp/omi-settings-seed-eager.out
assert_defaults "$eager_target" screenAnalysisEnabled 1
assert_defaults "$eager_target" transcriptionEnabled 1
assert_defaults "$eager_target" devLazyPermissionsEnabled 0
assert_unset "$eager_target" disableSystemAudioCapture
assert_unset "$eager_target" systemAudioCaptureMode
assert_unset "$eager_target" screenAnalysisAutoStartFixed_v2

"$MACOS_DIR/scripts/omi-settings-seed.sh" "$missing_target" "com.omi.missing-source-$$" >/tmp/omi-settings-seed-missing.out
assert_defaults "$missing_target" screenAnalysisEnabled 0
assert_defaults "$missing_target" transcriptionEnabled 0
assert_defaults "$missing_target" devLazyPermissionsEnabled 1

echo "settings-seed tests passed"
