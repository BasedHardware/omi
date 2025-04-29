#!/bin/bash
set -e

# Set up working directory
cd /omi/firmware/

# Initialize west with nRF Connect SDK if not already initialized
echo "Checking west initialization status..."
if [ ! -d "v2.7.0/.west" ]; then
    echo "Initializing west with nRF Connect SDK v2.7.0..."
    west init -m https://github.com/nrfconnect/sdk-nrf --mr v2.7.0 v2.7.0
else
    echo "West is already initialized in v2.7.0, using existing installation."
fi

# Navigate to SDK directory
cd v2.7.0

# Update west modules (only if not already up to date)
echo "Updating west modules..."
west update -o=--depth=1 -n || echo "West update failed, continuing with existing modules."
west blobs fetch hal_nordic || echo "Blob fetch failed, continuing with existing blobs."

# Configure environment
echo "Configuring build environment..."
west zephyr-export

# Build firmware with exact same parameters as used in the IDE
echo "Building firmware for xiao_ble/nrf52840/sense board..."
west build -b xiao_ble/nrf52840/sense --pristine always ../devkit -- \
    -DNCS_TOOLCHAIN_VERSION="NONE" \
    -DCONF_FILE="prj_xiao_ble_sense_devkitv2-adafruit.conf" \
    -DDTC_OVERLAY_FILE="/omi/firmware/devkit/overlay/xiao_ble_sense_devkitv2-adafruit.overlay" \
    -DCMAKE_EXPORT_COMPILE_COMMANDS="YES" \
    -DCMAKE_BUILD_TYPE="Debug" \
    -DPLATFORM=nrf52840 \
    -DCACHED_CONF_FILE="/omi/firmware/devkit/prj_xiao_ble_sense_devkitv2-adafruit.conf"

# Copy build artifacts to output directory
echo "Copying build artifacts to output directory..."
# The build output is in the 'build' directory within the SDK (v2.7.0/build)
mkdir -p /omi/firmware/build/docker_build
cp -r build/zephyr/zephyr.{hex,bin,uf2} /omi/firmware/build/docker_build/ || echo "Warning: Some build artifacts not found"

# Create OTA package
echo "Creating OTA package..."
cd /omi/firmware/build/docker_build/
adafruit-nrfutil dfu genpkg --dev-type 0x0052 --dev-revision 0xCE68 --application zephyr.hex zephyr.zip

echo ""
echo "==================================================="
echo "Build completed successfully!"
echo "Build artifacts are located at:"
echo "  /omi/firmware/build/docker_build/"
echo "  • zephyr.hex - Raw firmware hex file"
echo "  • zephyr.bin - Binary firmware file"
echo "  • zephyr.uf2 - UF2 firmware file for direct flashing"
echo "  • zephyr.zip - OTA update package"
echo "==================================================="