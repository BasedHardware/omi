#!/usr/bin/env bash
#
# PROTOTYPE build for the Omi CV1 firmware with the opt-in HID dictation
# feature compiled in. Same container and NCS workspace as
# scripts/ci/build-cv1.sh; adds omi/hid_dictation.conf as EXTRA_CONF_FILE and
# builds into build-hid/ so it never clobbers production artifacts.
#
# Runs INSIDE ghcr.io/zephyrproject-rtos/ci:<tag> with the repo's
# omi/firmware directory bind-mounted at /omi/firmware. Never shipped: this
# output is for David's device testing of the draft PR only.
#
set -euo pipefail

FW=/omi/firmware
NCS_VERSION=v2.9.0
BOARD=omi/nrf5340/cpuapp

git config --global --add safe.directory '*'

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

cp "$FW/omi/omi.conf" "$FW/omi/prj.conf"

echo "Building $BOARD (HID dictation prototype) with sysbuild..."
west build -b "$BOARD" "$FW/omi" --sysbuild -d build-hid --pristine always \
  -- -DBOARD_ROOT="$FW" -DEXTRA_CONF_FILE="$FW/omi/hid_dictation.conf"

test -s build-hid/dfu_application.zip
test -s build-hid/merged.hex
test -s build-hid/merged_CPUNET.hex

echo "CV1 HID prototype build complete:"
ls -l build-hid/dfu_application.zip build-hid/merged.hex build-hid/merged_CPUNET.hex
