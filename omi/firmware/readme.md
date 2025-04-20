# Omi Firmware

This repository contains the firmware for the Omi AI wearable device.

## Overview

The Omi firmware is built on the Zephyr RTOS and provides functionality for audio capture, processing, and battery. It includes Bluetooth connectivity for streaming audio data. Given the complex nature of this firmware its not buildable in Arduino IDE and requires a more advanced toolchain.

## Directory Structure

- `omi/`: The main application project files
    - `src/`: Source files for the application code
    - `lib/`: Libraries used by the application
    - `CMakeLists.txt`: CMake build configuration
    - `CMakePresets.json`: CMake presets configuration
- `devkit/`: The development kit application project files (for Omi DevKit1, Omi DevKit2)
    - `src/`: Source files specific to the devkit version
    - `lib/`: Libraries used by the devkit
    - `CMakeLists.txt`: CMake build configuration
    - `CMakePresets.json`: CMake presets configuration
- `test/`: The test project files
- `boards/`: Custom board definitions and configurations
- `scripts/`: Build and utility scripts

## Building the Firmware

There are two ways to build the firmware:

### Option 1: Using nRF Connect for VS Code

Prerequisites:
- [Visual Studio Code](https://code.visualstudio.com/)
- [nRF Connect for VS Code extension](https://marketplace.visualstudio.com/items?itemName=NordicSemiconductor.nrf-connect-for-visual-studio-code)
  - devkit: NCS 2.7.0
  - omi: NCS 2.9.0
- [nRF Command Line Tools](https://www.nordicsemi.com/Software-and-tools/Development-Tools/nRF-Command-Line-Tools/Download)

Follow the instructions in our [official documentation](https://docs.omi.me/docs/developer/Compile_firmware).

### Option 2: Using Docker

This is the easiest method and works across all platforms:

```bash
./scripts/build-docker.sh
```

For detailed instructions, see [docker-build.md](./scripts/docker-build.md).


## Flashing the Firmware

Follow the instructions at https://docs.omi.me/docs/get_started/Flash_device

For Docker builds, the output files will be in `build/docker_build/`.
For nRF Connect builds, locate the `zephyr.uf2` file in your build output directory.

## Device-Specific Builds

For different device hardware versions (e.g., V1 and V2), use separate overlay files and project configuration files. See `CMakePresets.json` for the available configurations.

These overlay files provide context on pins and device functions to the firmware when building. Each device will need its own unique build.

To select the appropriate overlay file select the configuration in the nRF Connect extension sidebar which is set in `CMakePresets.json`.

## Debugging

To enable USB serial debugging:

1. Uncomment the debug lines in `main.c`.
2. Use the nRF Terminal in VS Code to view debug output.
3. Full live-code debugging is also supported using the nRF Connect extension however this requires a J-Link debugger device and additional setup.

## Key Components

- **Main Application**: Coordinates the overall functionality of the device from initialization to shutdown.
- **Audio Capture**: Handles microphone input and audio buffering.
- **Codec**: Processes raw audio data.
- **Transport**: Manages Bluetooth connectivity and audio streaming.
- **Storage**: Handles SD card operations and audio file management.
- **LED Control**: Provides visual feedback about device status.

## On the Storage Reads

The storage will automatically activate whenever there is no Bluetooth connection to the app. Whenever you turn on the device, a new file is created which
will begin filling with opus encoded data. Whenever you connect to the app, the contents of the storage will begin streaming to the app. When it is finished, it will try to delete the file on the device.

The format of each packet is different to the streaming audio packets.
