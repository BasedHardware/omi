#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$MACOS_DIR/scripts/app-config.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_eq() {
  local expected="$1" actual="$2" label="$3"
  if [ "$expected" != "$actual" ]; then
    fail "$label: expected '$expected', got '$actual'"
  fi
}

assert_config() {
  local app_name="$1" expected_is_named="$2" expected_bundle="$3" expected_scheme="$4"
  derive_omi_app_config "$app_name"
  assert_eq "$app_name" "$APP_NAME" "APP_NAME for $app_name"
  assert_eq "$expected_is_named" "$IS_NAMED_BUNDLE" "IS_NAMED_BUNDLE for $app_name"
  assert_eq "$expected_bundle" "$EXPECTED_BUNDLE_ID" "EXPECTED_BUNDLE_ID for $app_name"
  assert_eq "$expected_scheme" "$EXPECTED_URL_SCHEME" "EXPECTED_URL_SCHEME for $app_name"
  assert_eq "$expected_bundle" "$BUNDLE_ID" "BUNDLE_ID for $app_name"
  assert_eq "$expected_scheme" "$URL_SCHEME" "URL_SCHEME for $app_name"
}

assert_config "Omi Dev" "false" "com.omi.desktop-dev" "omi-computer-dev"
assert_config "omi-subagent-test" "true" "com.omi.omi-subagent-test" "omi-omi-subagent-test"
assert_config "Omi Subagent Test!!" "true" "com.omi.omi-subagent-test" "omi-omi-subagent-test"

if derive_omi_app_config "!!!" >/tmp/omi-app-config-invalid.out 2>/tmp/omi-app-config-invalid.err; then
  fail "invalid app name unexpectedly succeeded"
fi
if ! grep -q "OMI_APP_NAME must contain at least one letter or number" /tmp/omi-app-config-invalid.err; then
  fail "invalid app name did not explain the slug requirement"
fi

if OMI_BUNDLE_ID="com.omi.wrong" derive_omi_app_config "omi-subagent-test" >/tmp/omi-app-config-bundle.out 2>/tmp/omi-app-config-bundle.err; then
  fail "mismatched OMI_BUNDLE_ID unexpectedly succeeded"
fi
if ! grep -q "must use bundle ID 'com.omi.omi-subagent-test'" /tmp/omi-app-config-bundle.err; then
  fail "mismatched OMI_BUNDLE_ID did not report expected bundle id"
fi

if OMI_URL_SCHEME="omi-wrong" derive_omi_app_config "omi-subagent-test" >/tmp/omi-app-config-scheme.out 2>/tmp/omi-app-config-scheme.err; then
  fail "mismatched OMI_URL_SCHEME unexpectedly succeeded"
fi
if ! grep -q "must use URL scheme 'omi-omi-subagent-test'" /tmp/omi-app-config-scheme.err; then
  fail "mismatched OMI_URL_SCHEME did not report expected URL scheme"
fi

echo "app-config tests passed"
