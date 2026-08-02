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
: "${MCUBOOT_SIGNING_KEY_FILE:?MCUBOOT_SIGNING_KEY_FILE must point to an injected signing key}"
test -f "$MCUBOOT_SIGNING_KEY_FILE"
test ! -f "$FW/bootloader/mcuboot/root-rsa-2048.pem"

# west/git operate on the bind-mounted tree owned by the host user; the
# container runs as root, so tell git the checkout is trusted.
git config --global --add safe.directory '*'

# MCUboot image signing needs the `ecdsa` python package (per BUILD.md).
pip3 install --quiet ecdsa 2>/dev/null || pip3 install --quiet --break-system-packages ecdsa

# The VERSION file drives MCUboot image signing, and CONFIG_MCUBOOT_DOWNGRADE_PREVENTION
# only means anything if that version is real and matches the advertised firmware
# revision. Keep the two in lockstep here rather than discovering the drift in the field.
APP_VERSION=$(awk -F'=' '
  /^VERSION_MAJOR/ {major=$2}
  /^VERSION_MINOR/ {minor=$2}
  /^PATCHLEVEL/    {patch=$2}
  END {gsub(/ /,"",major); gsub(/ /,"",minor); gsub(/ /,"",patch); print major "." minor "." patch}
' "$FW/omi/VERSION")
DIS_VERSION=$(sed -n 's/^CONFIG_BT_DIS_FW_REV_STR="\(.*\)"$/\1/p' "$FW/omi/omi.conf")

if [ -z "$APP_VERSION" ] || [ "$APP_VERSION" = "0.0.0" ]; then
  echo "ERROR: omi/firmware/omi/VERSION is missing or 0.0.0; MCUboot downgrade prevention would be a no-op." >&2
  exit 1
fi

if [ "$APP_VERSION" != "$DIS_VERSION" ]; then
  echo "ERROR: VERSION ($APP_VERSION) does not match CONFIG_BT_DIS_FW_REV_STR ($DIS_VERSION)." >&2
  exit 1
fi

echo "Building firmware version $APP_VERSION"

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
  -- -DBOARD_ROOT="$FW" -DSB_CONFIG_BOOT_SIGNATURE_KEY_FILE="$MCUBOOT_SIGNING_KEY_FILE"

# Fail loud if any expected artifact is missing (silent-drop prevention).
test -s build/dfu_application.zip
test -s build/merged.hex
test -s build/merged_CPUNET.hex

# CONFIG_MCUBOOT_DOWNGRADE_PREVENTION compares the signed image version. If the
# VERSION file did not reach imgtool every build signs 0.0.0+0, every image
# compares equal, and any older release artifact can be flashed back.
IMGTOOL="bootloader/mcuboot/scripts/imgtool.py"
SIGNED_IMAGE=$(find build -name 'zephyr.signed.bin' -print -quit)
if [ -z "$SIGNED_IMAGE" ]; then
  echo "ERROR: no signed image found; cannot verify the MCUboot image version." >&2
  exit 1
fi

SIGNED_VERSION=$(python3 "$IMGTOOL" verify "$SIGNED_IMAGE" | sed -n 's/.*[Ii]mage version: *//p' | head -n1)
echo "signed image version: ${SIGNED_VERSION:-<unreported>}"
case "$SIGNED_VERSION" in
  "" | 0.0.0*)
    echo "ERROR: signed image version is '${SIGNED_VERSION:-<unreported>}'." >&2
    echo "       MCUboot downgrade prevention is a no-op at 0.0.0. Check omi/firmware/omi/VERSION." >&2
    exit 1
    ;;
esac

echo "CV1 build complete:"
ls -l build/dfu_application.zip build/merged.hex build/merged_CPUNET.hex
