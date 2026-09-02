#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fixture_dir="$(mktemp -d "${TMPDIR:-/tmp}/omi-mobile-wrapper.XXXXXX")"
trap 'rm -rf "$fixture_dir"' EXIT

mkdir -p "$fixture_dir/scripts" "$fixture_dir/ios"
cp "$ROOT_DIR/setup.sh" "$fixture_dir/setup.sh"
cp "$ROOT_DIR/scripts/validate_mobile_build_config.sh" "$fixture_dir/scripts/validate_mobile_build_config.sh"
chmod +x "$fixture_dir/scripts/validate_mobile_build_config.sh"

log_file="$fixture_dir/flutter.log"
(
  cd "$fixture_dir"
  source ./setup.sh >/dev/null

  flutter() {
    {
      printf 'flutter'
      printf ' %s' "$@"
      printf '\n'
    } >>"$log_file"
  }
  pod() {
    {
      printf 'pod'
      printf ' %s' "$@"
      printf '\n'
    } >>"$log_file"
  }
  dart() {
    {
      printf 'dart'
      printf ' %s' "$@"
      printf '\n'
    } >>"$log_file"
  }
  check_ios_prerequisites() { :; }
  select_ios_device() { printf 'TEST-DEVICE\n'; }

  run_build_ios prod
  grep -F 'flutter run --flavor prod -d TEST-DEVICE --dart-define=OMI_APP_PROFILE=mobile_beta' "$log_file" >/dev/null
  [[ "$(grep -F 'OMI_APP_PROFILE=mobile_beta' "$log_file" | tr ' ' '\n' | grep -c '^--dart-define=')" == 1 ]]

  if run_build_ios prod --dart-define=OMI_APP_PROFILE=production; then
    echo 'FAIL: wrapper accepted a conflicting profile define' >&2
    exit 1
  fi
)

echo 'mobile build wrapper injects one required profile and rejects conflicts'
