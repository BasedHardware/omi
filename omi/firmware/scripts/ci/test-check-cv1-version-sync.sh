#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CHECK="$SCRIPT_DIR/check-cv1-version-sync.sh"
SET_VERSION="$SCRIPT_DIR/set-cv1-version.sh"
SYNC_RELEASE_VERSION="$SCRIPT_DIR/sync-cv1-release-version.sh"
TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/omi-cv1-version-sync.XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

write_config() {
  local dis_version=$1
  local mcuboot_version=${2-}
  local path=$3

  printf 'CONFIG_BT_DIS_FW_REV_STR="%s"\n' "$dis_version" >"$path"
  if [[ -n "$mcuboot_version" ]]; then
    printf 'CONFIG_MCUBOOT_IMGTOOL_SIGN_VERSION="%s"\n' "$mcuboot_version" >>"$path"
  fi
}

expect_failure() {
  local expected_message=$1
  local path=$2
  local output

  if output=$("$CHECK" "$path" 2>&1); then
    echo "error: expected version check to fail for $path" >&2
    exit 1
  fi
  if [[ "$output" != *"$expected_message"* ]]; then
    echo "error: expected '$expected_message', got: $output" >&2
    exit 1
  fi
}

"$CHECK"

write_config "3.0.26" "3.0.26+0" "$TEST_DIR/matching.conf"
"$CHECK" "$TEST_DIR/matching.conf"

write_config "3.0.26" "3.0.26+5" "$TEST_DIR/nonzero-build.conf"
cp "$TEST_DIR/nonzero-build.conf" "$TEST_DIR/nonzero-build.expected"
"$SYNC_RELEASE_VERSION" "$TEST_DIR/nonzero-build.conf" ""
cmp -s "$TEST_DIR/nonzero-build.expected" "$TEST_DIR/nonzero-build.conf"
grep -Fq 'CONFIG_MCUBOOT_IMGTOOL_SIGN_VERSION="3.0.26+5"' "$TEST_DIR/nonzero-build.conf"

write_config "3.0.26" "3.0.25+0" "$TEST_DIR/mismatch.conf"
expect_failure "does not match" "$TEST_DIR/mismatch.conf"
"$SYNC_RELEASE_VERSION" "$TEST_DIR/mismatch.conf" "v4.5.6"
grep -Fq 'CONFIG_BT_DIS_FW_REV_STR="4.5.6"' "$TEST_DIR/mismatch.conf"
grep -Fq 'CONFIG_MCUBOOT_IMGTOOL_SIGN_VERSION="4.5.6+0"' "$TEST_DIR/mismatch.conf"
"$CHECK" "$TEST_DIR/mismatch.conf"

write_config "3.0.26" "" "$TEST_DIR/missing-mcuboot.conf"
expect_failure "expected exactly one CONFIG_MCUBOOT_IMGTOOL_SIGN_VERSION" "$TEST_DIR/missing-mcuboot.conf"

write_config "3.0.26" "3.0.26" "$TEST_DIR/missing-build.conf"
expect_failure "must use X.Y.Z+N form" "$TEST_DIR/missing-build.conf"

write_config "3.0.26" "3.0.26+0" "$TEST_DIR/duplicate.conf"
printf 'CONFIG_BT_DIS_FW_REV_STR="3.0.27"\n' >>"$TEST_DIR/duplicate.conf"
expect_failure "expected exactly one CONFIG_BT_DIS_FW_REV_STR" "$TEST_DIR/duplicate.conf"

if "$SET_VERSION" "$TEST_DIR/matching.conf" "4.5" >/dev/null 2>&1; then
  echo "error: expected invalid release override to fail" >&2
  exit 1
fi

echo "CV1 version sync tests passed"
