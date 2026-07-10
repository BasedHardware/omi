#!/usr/bin/env bash
#
# CI build for the Omi CV1 firmware (nRF5340, the consumer "Omi CV 1" device).
#
# Runs INSIDE the ghcr.io/zephyrproject-rtos/ci:<tag> container with the repo's
# `omi/firmware` directory bind-mounted at /omi/firmware. Mirrors the blessed
# command documented in omi/firmware/omi/BUILD.md (NCS v2.9.0 + sysbuild +
# MCUboot signing) but initialises the west workspace from scratch so it works
# in a clean CI checkout (the v2.9.0 SDK is not committed).
#
# Outputs (relative to /omi/firmware/v2.9.0/build):
#   - dfu_application.zip   OTA package served by the Omi app
#   - merged.hex            full-flash image (J-Link / nrfjprog)
#   - merged_CPUNET.hex     network-core image
#
set -euo pipefail

FW=/omi/firmware
NCS_VERSION=v2.9.0
BOARD=omi/nrf5340/cpuapp

# west/git operate on the bind-mounted tree owned by the host user; the
# container runs as root, so tell git the checkout is trusted.
git config --global --add safe.directory '*'

# MCUboot image signing needs the `ecdsa` python package (per BUILD.md).
pip3 install --quiet ecdsa 2>/dev/null || pip3 install --quiet --break-system-packages ecdsa

cd "$FW"
mkdir -p "$NCS_VERSION"
cd "$NCS_VERSION"

if [ ! -d .west ]; then
  echo "Initialising nRF Connect SDK $NCS_VERSION workspace..."
  west init -m https://github.com/nrfconnect/sdk-nrf --mr "$NCS_VERSION" .
fi

echo "Updating west modules (shallow)..."
west update -o=--depth=1 -n
west zephyr-export

# The production config lives in omi.conf; Zephyr builds prj.conf by default,
# so copy it across. This keeps CONFIG_BT_DIS_FW_REV_STR (the firmware version
# baked into the binary) in sync with omi.conf, the release source of truth.
cp "$FW/omi/omi.conf" "$FW/omi/prj.conf"

echo "Building $BOARD with sysbuild..."
west build -b "$BOARD" "$FW/omi" --sysbuild -d build --pristine always \
  -- -DBOARD_ROOT="$FW"

# Fail loud if any expected artifact is missing (silent-drop prevention).
test -s build/dfu_application.zip
test -s build/merged.hex
test -s build/merged_CPUNET.hex

echo "CV1 build complete:"
ls -l build/dfu_application.zip build/merged.hex build/merged_CPUNET.hex
