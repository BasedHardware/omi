#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CHECK="$SCRIPT_DIR/check-cv1-ble-buffer-contract.sh"
TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/omi-cv1-ble-buffer-contract.XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

write_configs() {
  local app_count=$1
  local radio_count=$2
  local controller_count=$3

  printf 'CONFIG_BT_BUF_ACL_TX_COUNT=%s\n' "$app_count" >"$TEST_DIR/app.conf"
  printf 'CONFIG_BT_BUF_ACL_TX_COUNT=%s\n' "$radio_count" >"$TEST_DIR/radio.conf"
  printf 'CONFIG_BT_CTLR_SDC_TX_PACKET_COUNT=%s\n' "$controller_count" >>"$TEST_DIR/radio.conf"
}

"$CHECK"

write_configs 10 10 10
"$CHECK" "$TEST_DIR/app.conf" "$TEST_DIR/radio.conf"

write_configs 10 10 6
if output=$("$CHECK" "$TEST_DIR/app.conf" "$TEST_DIR/radio.conf" 2>&1); then
  echo "error: expected undersized controller TX pool to fail" >&2
  exit 1
fi
if [[ "$output" != *"must be at least both CV1 host ACL TX pools"* ]]; then
  echo "error: expected undersized-pool diagnostic, got: $output" >&2
  exit 1
fi

echo "CV1 BLE buffer contract tests passed"
