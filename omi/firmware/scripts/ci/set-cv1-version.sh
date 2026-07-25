#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CONF=${1:?usage: set-cv1-version.sh CONFIG VERSION}
VERSION=${2:?usage: set-cv1-version.sh CONFIG VERSION}

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "error: invalid CV1 semantic version: $VERSION" >&2
  exit 1
fi
if [[ ! -f "$CONF" ]]; then
  echo "error: CV1 config not found: $CONF" >&2
  exit 1
fi
if [[ $(grep -c '^CONFIG_BT_DIS_FW_REV_STR=' "$CONF" || true) -ne 1 ]]; then
  echo "error: expected exactly one CONFIG_BT_DIS_FW_REV_STR in $CONF" >&2
  exit 1
fi
if [[ $(grep -c '^CONFIG_MCUBOOT_IMGTOOL_SIGN_VERSION=' "$CONF" || true) -ne 1 ]]; then
  echo "error: expected exactly one CONFIG_MCUBOOT_IMGTOOL_SIGN_VERSION in $CONF" >&2
  exit 1
fi

TEMP_CONFIG=$(mktemp "${CONF}.tmp.XXXXXX")
trap 'rm -f "$TEMP_CONFIG"' EXIT

awk -v version="$VERSION" '
  /^CONFIG_BT_DIS_FW_REV_STR=/ {
    print "CONFIG_BT_DIS_FW_REV_STR=\"" version "\""
    next
  }
  /^CONFIG_MCUBOOT_IMGTOOL_SIGN_VERSION=/ {
    print "CONFIG_MCUBOOT_IMGTOOL_SIGN_VERSION=\"" version "+0\""
    next
  }
  { print }
' "$CONF" >"$TEMP_CONFIG"

mv "$TEMP_CONFIG" "$CONF"
trap - EXIT
"$SCRIPT_DIR/check-cv1-version-sync.sh" "$CONF"
