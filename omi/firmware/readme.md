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

## Building and flashing the Firmware

Follow the instructions in our [official documentation](https://docs.omi.me/doc/developer/firmware/Compile_firmware).

## Device-Specific Builds

For different device hardware versions (e.g., V1 and V2), use separate overlay files and project configuration files. See `CMakePresets.json` for the available configurations.

These overlay files provide context on pins and device functions to the firmware when building. Each device will need its own unique build.

To select the appropriate overlay file select the configuration in the nRF Connect extension sidebar which is set in `CMakePresets.json`.

## Debugging

To enable USB serial debugging:

### DevKit2

1. Clone this repository and edit `firmware/devkit/prj_xiao_ble_sense_devkitv2-adafruit.conf`.
2. Ensure the following settings are enabled (set to `y` and not commented out):
   - `CONFIG_CONSOLE=y`
   - `CONFIG_PRINTK=y`
   - `CONFIG_LOG=y`
   - `CONFIG_LOG_PRINTK=y`
   - `CONFIG_UART_CONSOLE=y`
3. Offline storage is currently experimental and must be disabled for logging. Ensure the following setting is disabled (set to `n` and not commented out):
   - `CONFIG_OMI_ENABLE_OFFLINE_STORAGE=n`
4. **NOTE:** Logging may be enabled with offline storage with the following settings. **These settings may affect the performance of data transfer via BLE or when writing to the SD card**:
   - `CONFIG_LOG_PROCESS_THREAD_PRIORITY=5`
   - `CONFIG_LOG_PROCESS_THREAD_CUSTOM_PRIORITY=y`
5. Build and flash the debugging firmware according to the instructions in the [official documentation](https://docs.omi.me/doc/developer/firmware/Compile_firmware).
6. Use the nRF Serial Terminal in VS Code to view debug output.

Full live-code debugging is also supported using the nRF Connect extension; however, this requires a J-Link debugger device and additional setup.

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
