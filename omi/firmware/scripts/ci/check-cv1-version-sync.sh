#!/usr/bin/env bash
#
# Keep the user-visible DIS version and MCUboot's image-comparison version in
# lockstep. A mismatch can install only one half of a dual-core CV1 OTA.
#
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
FIRMWARE_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
CONF=${1:-"$FIRMWARE_ROOT/omi/omi.conf"}

if [[ ! -f "$CONF" ]]; then
  echo "error: CV1 config not found: $CONF" >&2
  exit 1
fi

DIS_DEFINITION_COUNT=$(grep -c '^CONFIG_BT_DIS_FW_REV_STR=' "$CONF" || true)
MCUBOOT_DEFINITION_COUNT=$(grep -c '^CONFIG_MCUBOOT_IMGTOOL_SIGN_VERSION=' "$CONF" || true)

if [[ "$DIS_DEFINITION_COUNT" -ne 1 ]]; then
  echo "error: expected exactly one CONFIG_BT_DIS_FW_REV_STR in $CONF" >&2
  exit 1
fi
if [[ "$MCUBOOT_DEFINITION_COUNT" -ne 1 ]]; then
  echo "error: expected exactly one CONFIG_MCUBOOT_IMGTOOL_SIGN_VERSION in $CONF" >&2
  exit 1
fi

DIS_VERSION=$(sed -n 's/^CONFIG_BT_DIS_FW_REV_STR="\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\)"$/\1/p' "$CONF")
MCUBOOT_VERSION=$(sed -n \
  's/^CONFIG_MCUBOOT_IMGTOOL_SIGN_VERSION="\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\)+[0-9][0-9]*"$/\1/p' \
  "$CONF")

if [[ -z "$DIS_VERSION" ]]; then
  echo "error: CONFIG_BT_DIS_FW_REV_STR must use semantic X.Y.Z form in $CONF" >&2
  exit 1
fi
if [[ -z "$MCUBOOT_VERSION" ]]; then
  echo "error: CONFIG_MCUBOOT_IMGTOOL_SIGN_VERSION must use X.Y.Z+N form in $CONF" >&2
  exit 1
fi

if [[ "$DIS_VERSION" != "$MCUBOOT_VERSION" ]]; then
  echo "error: CV1 DIS version $DIS_VERSION does not match MCUboot version $MCUBOOT_VERSION in $CONF" >&2
  exit 1
fi

echo "CV1 firmware versions agree: $DIS_VERSION"
