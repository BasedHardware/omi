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
#   - merged.hex            internal merged output; not an approved wire image
#   - merged_CPUNET.hex     network-core image
#
set -euo pipefail

FW=/omi/firmware
NCS_VERSION=v2.9.0
NCS_REVISION=7787b264984022cda64d9629278942053e6462a5
export SOURCE_DATE_EPOCH=0 PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8
export CMAKE_BUILD_PARALLEL_LEVEL=2
export NINJAFLAGS=-j2
BOARD=omi/nrf5340/cpuapp

# west/git operate on the bind-mounted tree owned by the host user; the
# container runs as root, so tell git the checkout is trusted.
git config --global --add safe.directory '*'

# MCUboot image signing needs the `ecdsa` python package (per BUILD.md).
pip3 install --quiet ecdsa==0.19.0 2>/dev/null || pip3 install --quiet --break-system-packages ecdsa==0.19.0

# Verify CV1 MTU notification limit contract
python3 "$FW/scripts/check_cv1_mtu.py" "$FW/omi/src/lib/core/transport.c"


cd "$FW"
mkdir -p "$NCS_VERSION"
cd "$NCS_VERSION"

if [ ! -d .west ]; then
  echo "Initialising nRF Connect SDK $NCS_VERSION workspace..."
  # This west version bootstraps with git clone --branch, which cannot take a SHA.
  # The tag only initializes the workspace; the immutable checkout below owns
  # every manifest/module revision used by the build.
  west init -m https://github.com/nrfconnect/sdk-nrf --mr "$NCS_VERSION" .
fi

# Cached workspaces must use the same immutable manifest as a cold build.
git -C nrf fetch --depth=1 origin "$NCS_REVISION"
git -C nrf checkout --detach "$NCS_REVISION"
echo "Updating west modules (shallow)..."
west update -o=--depth=1 -n
west zephyr-export

# Select the production app config through sysbuild's image-scoped setting.
# Do not create an untracked prj.conf: the later simulator gate requires a
# clean firmware checkout when it records the exact source SHA.
echo "Building $BOARD with sysbuild..."
west build -o=-j2 -b "$BOARD" "$FW/omi" --sysbuild -d build --pristine always \
  -- -DBOARD_ROOT="$FW" -Domi_CONF_FILE="$FW/omi/omi.conf" -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

# Fail loud if any expected artifact is missing (silent-drop prevention).
test -s build/omi/zephyr/zephyr.elf
test -s build/dfu_application.zip
test -s build/merged.hex
test -s build/merged_CPUNET.hex

echo "CV1 build complete:"
ls -l build/dfu_application.zip build/merged.hex build/merged_CPUNET.hex

# Evidence is a QA artifact, never a release asset. Extract exactly the boot
# reservation with 0xff holes; never include UICR or a network image.
COMPILER=$(sed -n 's/^CMAKE_C_COMPILER:[^=]*=//p' build/mcuboot/CMakeCache.txt)
test -x "$COMPILER"
OBJDUMP="${COMPILER%gcc}objdump"
test -x "$OBJDUMP"
python3 "$FW/scripts/ci/prove_cv1_bootloader.py" --build build \
  --objdump "$OBJDUMP" --out build/cv1-bootloader
# Prove reproducibility of the unsigned bootloader, independently of the app's
# randomized RSA signature. Keep all paths and the pinned toolchain unchanged.
cp build/cv1-bootloader/cv1-mcuboot.bin build/cv1-mcuboot-first.bin
cmake --build build/mcuboot --target clean
cmake --build build/mcuboot --parallel 2
python3 "$FW/scripts/ci/prove_cv1_bootloader.py" --build build \
  --objdump "$OBJDUMP" --out build/cv1-bootloader
cmp build/cv1-mcuboot-first.bin build/cv1-bootloader/cv1-mcuboot.bin
printf '%s\n' 'Two clean MCUboot compilations produced identical 64KiB boot regions.' \
  > build/cv1-bootloader/reproducibility.txt
# west 1.2.0 freezes inactive projects too, even when west update correctly
# leaves them uncloned. Record the resolved pinned manifest and actual active
# module SHAs without cloning modules that are not part of this build.
west manifest --resolve > build/cv1-bootloader/west-resolved.yml
west list -f '{name} {path} {sha}' > build/cv1-bootloader/west-active-shas.txt
git -C nrf rev-parse HEAD > build/cv1-bootloader/ncs-revision.txt
"$COMPILER" --version > build/cv1-bootloader/toolchain.txt
