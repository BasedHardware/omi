# Flashing ESP32 S3 XIAO Firmware with PlatformIO

This guide explains how to flash the OpenGlass firmware to your ESP32 S3 XIAO board using PlatformIO.

## Prerequisites

- PlatformIO installed on your system
- ESP32 S3 XIAO board connected via USB
- USB drivers for the ESP32 board (usually installed automatically)

## Installation

If you haven't installed PlatformIO yet, you can install it using:

### macOS:
```bash
brew install platformio
```

### Windows/Linux:
```bash
pip install platformio
```

## Project Structure

The firmware has been adapted to use PlatformIO:
- `platformio.ini`: Configuration file for PlatformIO with two environments:
  - `seeed_xiao_esp32s3`: Standard environment with 115200 baud upload speed
  - `seeed_xiao_esp32s3_slow`: Slower environment with 57600 baud upload speed for more reliable flashing
- `src/main.cpp`: Main source code (adapted from firmware.ino)
- `src/camera_pins.h` and `src/mulaw.h`: Required header files

## Flashing the Firmware

We provide multiple ways to flash your ESP32 S3 XIAO board:

### Option 1: Using the Python Script (Recommended)
The Python script provides an interactive way to flash your board:

1. Connect your ESP32 S3 XIAO board to your computer via USB
2. Run the Python script:
   ```bash
   python3 ./flash_esp32.py
   ```
3. Follow the on-screen instructions to:
   - Select the correct port
   - Put your board in bootloader mode
   - Flash the firmware

### Option 2: Using the Bash Script
1. Connect your ESP32 S3 XIAO board to your computer via USB
2. Run the bash script:
   ```bash
   ./flash_esp32.sh
   ```
3. Follow the on-screen instructions

### Option 3: Manual Method
1. Connect your ESP32 S3 XIAO board to your computer via USB
2. Put the board in bootloader mode (see below)
3. Run the following commands:
   ```bash
   # Try standard environment first
   platformio run -e seeed_xiao_esp32s3 --target upload --upload-port YOUR_PORT
   
   # If the above fails, try the slower environment
   platformio run -e seeed_xiao_esp32s3_slow --target upload --upload-port YOUR_PORT
   
   # Monitor the serial output
   platformio device monitor -p YOUR_PORT -b 115200
   ```
   Replace `YOUR_PORT` with the actual port (e.g., `/dev/tty.usbmodem11401`)

## Entering Bootloader Mode

The ESP32 S3 XIAO needs to be in bootloader mode for flashing. To enter bootloader mode:

1. Press and hold the BOOT button on your ESP32 S3 XIAO
2. While holding BOOT, press the RESET button
3. Release the RESET button first, then release the BOOT button
4. Sometimes you need to press and hold the BOOT button again during the actual flashing process

## Troubleshooting

### "No serial data received" Error
If you encounter the "No serial data received" error:

1. Make sure your board is in bootloader mode (see above)
2. Try the slower upload environment:
   ```bash
   platformio run -e seeed_xiao_esp32s3_slow --target upload --upload-port YOUR_PORT
   ```
3. Try a different USB cable
4. Connect directly to your computer (not through a hub)
5. Try both scripts provided (Python and Bash)

### Cannot Find Device
If the upload fails because the device cannot be found:
1. Check the USB connection
2. Make sure your computer recognizes the device
3. Try pressing the reset button on the ESP32 S3
4. Try a different USB port
5. Check if you need to install CH340/CP210x drivers for your board
6. On macOS, make sure to allow the device in System Settings > Privacy & Security

### Upload Fails
If the upload fails with other errors:
1. Try pressing and holding the BOOT button during the upload process
2. Make sure your board has sufficient power (use a powered USB port)
3. Try a different USB cable
4. Connect directly to your computer (not through a hub)
5. If all else fails, try using the Arduino IDE with the ESP32 boards package installed

## Original Arduino-CLI Method

The original firmware used arduino-cli as described in the main README.md. You can still use that method if you prefer. 