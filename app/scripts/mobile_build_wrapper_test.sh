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

  # OMI_MOBILE_BUILD_MODE: debug (default) adds no mode flag; profile/release
  # add exactly one. Regression: a dev debug build on a physical iPhone crashed
  # at launch as soon as flutter run disconnected (iOS refuses a JIT Dart VM
  # without tooling), and nothing in the wrapper offered the AOT alternative.
  : >"$log_file"
  run_build_ios dev
  grep -F 'flutter run --flavor dev -d TEST-DEVICE --dart-define=OMI_APP_PROFILE=local_dev' "$log_file" >/dev/null
  if grep -E -- '--profile|--release' "$log_file" >/dev/null; then
    echo 'FAIL: default build mode added a profile/release flag' >&2
    exit 1
  fi

  : >"$log_file"
  OMI_MOBILE_BUILD_MODE=profile run_build_ios dev
  grep -F 'flutter run --flavor dev -d TEST-DEVICE --dart-define=OMI_APP_PROFILE=local_dev --profile' "$log_file" >/dev/null

  : >"$log_file"
  OMI_MOBILE_BUILD_MODE=release run_build_android dev
  grep -E '^flutter run --flavor dev .*--release$' "$log_file" >/dev/null

  : >"$log_file"
  if OMI_MOBILE_BUILD_MODE=bogus run_build_ios dev 2>/dev/null; then
    echo 'FAIL: wrapper accepted an unknown OMI_MOBILE_BUILD_MODE' >&2
    exit 1
  fi
  if grep -F 'flutter run' "$log_file" >/dev/null; then
    echo 'FAIL: wrapper ran flutter with an unknown OMI_MOBILE_BUILD_MODE' >&2
    exit 1
  fi

  # A debug build headed for a physical iPhone gets the untethered-crash
  # warning naming the fix; an AOT build does not.
  _ios_device_is_physical() { return 0; }
  warning_file="$fixture_dir/warning.log"
  OMI_DEV_HOST=192.168.1.2 run_build_ios dev 2>"$warning_file"
  grep -F 'OMI_MOBILE_BUILD_MODE=profile' "$warning_file" >/dev/null
  OMI_DEV_HOST=192.168.1.2 OMI_MOBILE_BUILD_MODE=profile run_build_ios dev 2>"$warning_file"
  if grep -F 'OMI_MOBILE_BUILD_MODE=profile' "$warning_file" >/dev/null; then
    echo 'FAIL: profile build still warned about the untethered debug crash' >&2
    exit 1
  fi
)

echo 'mobile build wrapper injects one required profile, rejects conflicts, and honors OMI_MOBILE_BUILD_MODE'
