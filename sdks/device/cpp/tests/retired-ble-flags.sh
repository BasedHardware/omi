#!/usr/bin/env bash
# Regression guard: a consumer still passing the retired SimpleBLE flags must
# fail at configure time with a migration message, never configure silently and
# then throw BleDisabled on the first Scan/Listen at runtime.
set -uo pipefail

cpp_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

failures=0

expect_configure_failure() {
  local flag="$1"
  local build_dir="$work_dir/${flag}"
  local output
  output="$(cmake -S "$cpp_dir" -B "$build_dir" "-D${flag}=ON" 2>&1)"
  local status=$?
  # CMake word-wraps message() output, so match against a single flattened line.
  local flat
  flat="$(tr '\n' ' ' <<<"$output" | tr -s ' ')"

  if [ "$status" -eq 0 ]; then
    echo "FAIL: -D${flag}=ON configured successfully; it must be a hard error"
    failures=$((failures + 1))
    return
  fi
  if ! grep -q "was removed along with the SimpleBLE dependency" <<<"$flat"; then
    echo "FAIL: -D${flag}=ON failed without the migration message:"
    echo "$output"
    failures=$((failures + 1))
    return
  fi
  if ! grep -q "SetBleBackend" <<<"$flat"; then
    echo "FAIL: -D${flag}=ON message does not name the replacement API"
    failures=$((failures + 1))
    return
  fi
  echo "ok: -D${flag}=ON fails at configure time with the migration message"
}

expect_clean_configure() {
  local build_dir="$work_dir/clean"
  if ! cmake -S "$cpp_dir" -B "$build_dir" >/dev/null 2>&1; then
    echo "FAIL: a plain configure must still succeed"
    failures=$((failures + 1))
    return
  fi
  echo "ok: plain configure succeeds"
}

expect_configure_failure OMI_DEVICE_BLE
expect_configure_failure OMI_DEVICE_SIMPLEBLE_SOURCE_DIR
expect_clean_configure

if [ "$failures" -ne 0 ]; then
  echo "$failures check(s) failed"
  exit 1
fi
echo "all retired-flag checks passed"
