# Building Firmware with Docker

This document explains how to build the firmware using Docker, which provides a consistent environment across different platforms (Linux, macOS, Windows). This is the **recommended** method for building the Omi firmware as it eliminates environment setup complexities.

> **Note:** For the traditional nRF Connect build method, see our [official documentation](https://docs.omi.me/docs/developer/Compile_firmware).

## Prerequisites

1. [Docker](https://www.docker.com/products/docker-desktop/) installed on your system
2. Git repository cloned to your local machine

## Building the Firmware

### Quick Start

From the root of the repository, run:

```bash
chmod +x omi/firmware/scripts/build-docker.sh
./omi/firmware/scripts/build-docker.sh
```

This script will:
1. Start a Docker container with the Zephyr RTOS build environment
2. Install necessary tools and dependencies
3. Build the firmware for the xiao_ble/nrf52840/sense board
4. Create an OTA package at `firmware/build/docker_build/zephyr.zip`
5. Show the location of all build artifacts

The build configuration exactly matches what would be produced by nRF Connect for VS Code, ensuring compatibility with the official build process.

### Clean Build

If you want to start fresh or are experiencing issues with an existing build, use the clean option:

```bash
./omi/firmware/scripts/build-docker.sh --clean
```

This will remove any existing SDK and build directories before starting the build process.

### Incremental Builds

By default, the build script will reuse an existing west installation and dependencies. This saves time by not re-downloading ~5GB of data on each build.

### Build Outputs

After a successful build, you will find these files in the `firmware/build/docker_build` directory:

- `zephyr.hex` - Raw firmware hex file
- `zephyr.bin` - Binary firmware file
- `zephyr.uf2` - UF2 firmware file for direct flashing to the device
- `zephyr.zip` - OTA update package

## Available Board Configurations

The firmware has several configuration files for different board variants:

1. `prj_xiao_ble_sense_devkitv2-adafruit.conf` - For the DevKit V2 with Adafruit bootloader (default)
2. `prj_xiao_ble_sense_devkitv1.conf` - For the DevKit V1
3. `prj_xiao_ble_sense_devkitv1-spisd.conf` - For the DevKit V1 with SPI SD card

The build also uses the corresponding overlay file from `app/overlay/`.

## Build Parameters

The Docker build uses the exact same build parameters as nRF Connect for VS Code:
- Configuration file: `prj_xiao_ble_sense_devkitv2-adafruit.conf`
- Device Tree Overlay: `overlay/xiao_ble_sense_devkitv2-adafruit.overlay`
- Build Type: Debug
- Platform: nrf52840

This ensures the Docker-built firmware is identical to one built with the IDE.

## Script Details

The repository contains two scripts for Docker-based firmware building:

1. `build-docker.sh` - The main script you run on your host machine. It sets up and runs the Docker container.
2. `build-firmware-in-docker.sh` - The script that runs inside the Docker container to build the firmware.

## Manual Build Process

If you prefer to run the Docker commands manually, you can use:

```bash
# Run from the root of the repository
docker run --rm -it -v "$(pwd):/omi" -e CMAKE_PREFIX_PATH=/opt/toolchains -e PATH="/root/.local/bin:$PATH" ghcr.io/zephyrproject-rtos/ci bash
pip install --user adafruit-nrfutil
cd /omi/firmware/
west init -m https://github.com/nrfconnect/sdk-nrf --mr v2.7.0 v2.7.0
cd v2.7.0
west update -o=--depth=1 -n
west blobs fetch hal_nordic
west zephyr-export
west build -b xiao_ble/nrf52840/sense --pristine always ../app -- \
    -DNCS_TOOLCHAIN_VERSION="NONE" \
    -DCONF_FILE="prj_xiao_ble_sense_devkitv2-adafruit.conf" \
    -DDTC_OVERLAY_FILE="/omi/firmware/devkit/overlay/xiao_ble_sense_devkitv2-adafruit.overlay" \
    -DCMAKE_EXPORT_COMPILE_COMMANDS="YES" \
    -DCMAKE_BUILD_TYPE="Debug" \
    -DPLATFORM=nrf52840 \
    -DCACHED_CONF_FILE="/omi/firmware/devkit/prj_xiao_ble_sense_devkitv2-adafruit.conf"
```

## Compatibility Notes

### Apple Silicon (M1/M2/M3 Macs)

The script automatically detects Apple Silicon (arm64) architecture and uses the compatible Docker image. No additional configuration is needed.

### Windows

On Windows, you may need to adjust the path mapping in the Docker command:

```bash
docker run --rm -it -v %cd%:/omi -e CMAKE_PREFIX_PATH=/opt/toolchains ghcr.io/zephyrproject-rtos/ci bash
```

## Flashing the Firmware

After building, copy the `zephyr.uf2` file to the device:

1. Put the XIAO board in bootloader mode by double-pressing the reset button
2. The board should appear as a USB drive (named XIAO-SENSE)
3. Copy the `zephyr.uf2` file to the root of this drive
4. The board will automatically reset after the firmware is flashed

For macOS:
```bash
cp firmware/build/docker_build/zephyr.uf2 /Volumes/XIAO-SENSE/
```

For Linux:
```bash
cp firmware/build/docker_build/zephyr.uf2 /path/to/XIAO-SENSE/
```

For Windows:
```bash
copy firmware\firmware\build\docker_build\zephyr.uf2 D:\
```
(where D: is the drive letter of the XIAO-SENSE board)

For more detailed flashing instructions, see our [official documentation](https://docs.omi.me/docs/get_started/Flash_device).
