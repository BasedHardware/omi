# OmiGlass Firmware v2.3.2

This directory contains the firmware binary for OmiGlass version 2.3.2.

## Release Information

- **Version:** 2.3.2
- **Date:** January 31, 2026
- **Hardware:** ESP32-S3 XIAO Sense
- **Branch:** omiglass-firmware-improvements

## Firmware File

- `omiglass_firmware_v2.3.2.bin` - Main firmware binary for OTA updates

## Installation

### Method 1: OTA Update via App
1. Upload the .bin file as a GitHub release asset
2. The app will automatically detect and offer the update
3. Requirement: device must be on firmware v2.3.1 or newer

### Method 2: Direct Flash via PlatformIO
```bash
cd omiGlass/firmware
platformio run -e seeed_xiao_esp32s3 --target upload
```

See the [Flash Firmware documentation](https://docs.omi.me/doc/hardware/omiglass/flash-firmware) for detailed instructions.

## Changes in 2.3.2

This release is from the `omiglass-firmware-improvements` branch for testing new features and improvements.

## GitHub Release Instructions

To create a GitHub release for OTA updates:

1. Create a new release with tag: `OmiGlass_v2.3.2`
2. Upload `omiglass_firmware_v2.3.2.bin` as an asset
3. Add the following metadata to the release description:

```markdown
<!-- KEY_VALUE_START
release_firmware_version:v2.3.2
minimum_firmware_required:v2.3.1
minimum_app_version:1.0.50
minimum_app_version_code:200
changelog:Firmware improvements from omiglass-firmware-improvements branch
KEY_VALUE_END -->
```
