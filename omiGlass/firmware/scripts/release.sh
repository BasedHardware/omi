#!/bin/bash

# A script to create a firmware release zip file
# Usage: ./release.sh <version>

set -e

if [ $# -lt 1 ]; then
    echo "Usage: $0 <version>"
    echo "Example: $0 1.0.0"
    exit 1
fi

VERSION=$1
ENV="seeed_xiao_esp32s3"

echo "Creating OMI Glass firmware release v$VERSION..."

# Check if we're in the firmware directory
if [ ! -f "platformio.ini" ]; then
    echo "Error: platformio.ini not found. Please run this script from the firmware directory."
    exit 1
fi

# Build the firmware
echo "Building firmware..."
pio run --environment $ENV

# Find the generated bin file in the correct location
BIN_FILE=".pio/build/$ENV/firmware.bin"
if [ ! -f "$BIN_FILE" ]; then
    # Try alternative path
    BIN_FILE=".pio/build/$ENV/firmware.elf.bin"
    if [ ! -f "$BIN_FILE" ]; then
        echo "Error: Binary file not found at expected locations:"
        echo "  - .pio/build/$ENV/firmware.bin"
        echo "  - .pio/build/$ENV/firmware.elf.bin"
        exit 1
    fi
fi

echo "Bin file created: $BIN_FILE"

# Create temp directory for package
TEMP_DIR="firmware_package"
rm -rf $TEMP_DIR
mkdir $TEMP_DIR
cp $BIN_FILE $TEMP_DIR/firmware.bin

# Create README
cat > $TEMP_DIR/README.txt << EOF
OMI Glass Firmware v$VERSION
=======================

Installation Instructions:
1. Put your ESP32-S3 in bootloader mode:
   - Hold BOOT button
   - Press and release RESET button
   - Release BOOT button
   - Device should appear as 'ESP32S3' USB drive

2. Copy firmware.bin to the ESP32S3 drive
3. Device will automatically flash and reboot

For more information, visit: https://github.com/BasedHardware/omi
EOF

# Create GitHub release template
GITHUB_TEMPLATE="<!-- KEY_VALUE_START
release_firmware_version:$VERSION
minimum_firmware_required:1.0.0
minimum_app_version:1.0.0
minimum_app_version_code:1
changelog:New firmware release v$VERSION
KEY_VALUE_END -->"

# Create zip file   
ZIP_FILE="openglass_firmware_v${VERSION}_ota.zip"
(cd $TEMP_DIR && zip -r ../$ZIP_FILE .)

# Clean up
rm -rf $TEMP_DIR

echo "✅ Release package created: $ZIP_FILE"
echo "Upload this file to GitHub releases"

echo "
GitHub Release Template:"
echo "--------------------"
echo "$GITHUB_TEMPLATE"
echo "--------------------"
