# Friend Hardware Firmware

This repository contains the firmware for the Friend AI wearable device.

## Overview

The Friend firmware is built on the Zephyr RTOS and provides functionality for audio capture, processing, and battery. It includes Bluetooth connectivity for streaming audio data. Given the complex nature of this firmware its not buildable in Arduino IDE and requires a more advanced toolchain.

## Directory Structure

- `src/`: Contains the source code files
- `include/`: Header files
- `boards/`: Board-specific configurations (not used)
- `overlays/`: Device-specific overlay files
- `CMakeLists.txt`: CMake build configuration
- `prj.conf`: Project configuration file

## Prerequisites

- (Visual Studio Code)[https://code.visualstudio.com/]
- (nRF Connect for VS Code extension)[https://marketplace.visualstudio.com/items?itemName=NordicSemiconductor.nrf-connect-for-visual-studio-code]
- (nRF Command Line Tools)[https://www.nordicsemi.com/Software-and-tools/Development-Tools/nRF-Command-Line-Tools/Download]

## Building the Firmware

1. Open the project in Visual Studio Code.
2. Install the recommended VS Code extensions when prompted.
3. Use the nRF Connect extension to build the firmware:
   - Open the nRF Connect extension sidebar.
   - Select your project configuration.
   - Click on "Build" in the extension's toolbar.

## Flashing the Firmware

1. Double-tap the reset button on your device to enter bootloader mode. This will open a USB drive on your computer which is used for flashing.
2. Locate the `zephyr.uf2` file in your build output directory.
3. Copy the `zephyr.uf2` file to the USB drive that appeared when you put the device in bootloader mode.
4. The device will automatically flash and restart with the new firmware.

## Device-Specific Builds

For different device versions (e.g., V1 and V2), use separate overlay files. For now a single device overlay file is provided for the V1 device.

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
