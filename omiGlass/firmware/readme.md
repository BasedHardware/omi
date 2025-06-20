# Using arduino-cli

### Install the board

```bash
arduino-cli config add board_manager.additional_urls https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
arduino-cli core install esp32:esp32@2.0.17
```

### Get board details

On Windows 11 board should be showing as ```esp32:esp32:XIAO_ESP32S3```
but instead might show as ```esp32:esp32:nora_w10```, ```esp32:esp32:wifiduino32c3```, or something else.

```bash
arduino-cli board list
arduino-cli board details -b esp32:esp32:XIAO_ESP32S3
```

### Compile and upload

Change COM5 to the port name from the board list output

```bash
arduino-cli compile --build-path build --output-dir dist -e -u -p COM5 -b esp32:esp32:XIAO_ESP32S3:PSRAM=opi
```

### Opus support

Go to your Arduino libraries folder.

You can get the libraries folder location with the following command:

```bash
arduino-cli config get directories.user
```

Note: You have to add ```/libraries``` to the path to get the libraries folder.

Then clone the two libraries needed to add Opus support:

```bash
git clone https://github.com/pschatzmann/arduino-libopus.git
git clone https://github.com/pschatzmann/arduino-audio-tools.git
```

## Troubleshoots

### A fatal error occurred: Failed to connect to ESP32-S3: No serial data received.
> For troubleshooting steps visit: https://docs.espressif.com/projects/esptool/en/latest/troubleshooting.html
> Error during Upload: Failed uploading: uploading error: exit status 2```

This is a very common and often frustrating error when working with ESP32 boards. The message Failed to connect to ESP32-S3: No serial data received means exactly
what it says: your computer sent a command to the omiGlass hardware to begin the upload process, but it received absolutely no data in response. The board was
silent.

Based on the troubleshooting guide you provided and common issues with the XIAO ESP32-S3, here is a step-by-step guide to fix this, starting with the most likely
cause.

                                                      The Most Likely Solution: Manually Enter Bootloader Mode

The XIAO ESP32-S3, like many ESP32 boards, sometimes fails to automatically enter "download mode" when the upload tool requests it. You need to force it into this
mode manually.

The XIAO ESP32-S3 has two small buttons on it: B (Boot) and R (Reset).

Here is the sequence to manually enter bootloader mode:

 1 Hold down the B (Boot) button.
 2 While still holding the B button, press and release the R (Reset) button.
 3 You can now release the B button.

The board is now in download mode and will wait for an upload command.

Your new workflow should be:

 1 Perform the manual bootloader sequence above.
 2 Immediately run your arduino-cli compile --upload ... command.

The upload should now proceed without the "No serial data received" error.
