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

For different device versions (e.g., V1 and V2), use separate overlay files and project configuration files. See `CMakePresets.json` for the available configurations.

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
The storage will automatically activate whenever there is no bluetooth connection to the app. Whenever you turn on the device, a new file is created which
will begin filling with opus encoded data. Whenever you connect to the app, the contents of the storage will begin streaming to the app. When it is finished, it will try to delete the file on the device.

The format of each packet is similar to the mic packets: that is, there is a 3 byte header denoting the order of packet arrival. The fourth bit is the number of bytes contained in the opus packet. The next bytes are the opus bytes themselves. The rest can be ignored.
Each packet (for now) is 83 bytes each for ease of transmission.

You don't need the app to test! Simply insert your device id in the file get_audio_file.py, and then run the file. If you want to decode the current file, then run decode_audio.py afterwards. There are some numbers that get sent by the device as a format
of acknowledgement. All of them are one byte each, so check for these status codes by checking the message lengths. Here are the important ones:

0 - This means the command was successfully parsed by the device. This means the start of transmission of audio data or deletion of a file.

100 - This number means the end of the audio transmission. You can know that the transmission ended with this code.

1,2,3,4,5 - These usually denote some error bits. They also mean that the device rejects the command and no transmission/deletion happens as a result.

Messages to the device take the form [a,b] or [a,b,c,d,e,f], where a denotes (0 for read) and (1 for delete), while b denotes the file number (1 is the first file, 2 is the second, etc. There is no notion of a 0th file). The optional [c,d,e,f] bytes denote the offset in uint format
in case you want to read from a file at some offset.

