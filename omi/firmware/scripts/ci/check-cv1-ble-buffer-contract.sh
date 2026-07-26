#!/usr/bin/env bash
#
# Keep the network controller's Link Layer TX pool deep enough to service both
# host-side ACL TX pools. An undersized controller pool throttles large CV1 BLE
# notifications before either host queue is full.
#
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
FIRMWARE_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
APP_CONF=${1:-"$FIRMWARE_ROOT/omi/omi.conf"}
RADIO_CONF=${2:-"$FIRMWARE_ROOT/omi/sysbuild/ipc_radio.conf"}

read_uint_config() {
  local config=$1
  local key=$2
  local definition_count
  local value

  if [[ ! -f "$config" ]]; then
    echo "error: CV1 config not found: $config" >&2
    return 1
  fi

  definition_count=$(grep -c "^${key}=" "$config" || true)
  if [[ "$definition_count" -ne 1 ]]; then
    echo "error: expected exactly one $key in $config" >&2
    return 1
  fi

  value=$(sed -n "s/^${key}=\\([0-9][0-9]*\\)$/\\1/p" "$config")
  if [[ -z "$value" ]]; then
    echo "error: $key must be an unsigned integer in $config" >&2
    return 1
  fi

  printf '%s\n' "$value"
}

APP_ACL_TX_COUNT=$(read_uint_config "$APP_CONF" CONFIG_BT_BUF_ACL_TX_COUNT)
RADIO_ACL_TX_COUNT=$(read_uint_config "$RADIO_CONF" CONFIG_BT_BUF_ACL_TX_COUNT)
CONTROLLER_TX_PACKET_COUNT=$(read_uint_config "$RADIO_CONF" CONFIG_BT_CTLR_SDC_TX_PACKET_COUNT)

if ((CONTROLLER_TX_PACKET_COUNT < APP_ACL_TX_COUNT ||
  CONTROLLER_TX_PACKET_COUNT < RADIO_ACL_TX_COUNT)); then
  echo "error: CONFIG_BT_CTLR_SDC_TX_PACKET_COUNT=$CONTROLLER_TX_PACKET_COUNT must be at least both CV1 host ACL TX pools (app=$APP_ACL_TX_COUNT, radio=$RADIO_ACL_TX_COUNT)" >&2
  exit 1
fi

echo "CV1 BLE TX buffer contract passes: app=$APP_ACL_TX_COUNT radio=$RADIO_ACL_TX_COUNT controller=$CONTROLLER_TX_PACKET_COUNT"
