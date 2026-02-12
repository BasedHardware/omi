# OmiGlass Firmware v2.3.1 — Flashing Guide (Windows)

This folder contains prebuilt firmware binaries for OmiGlass v2.3.1:

- `bootloader.bin`
- `partitions.bin`
- `firmware.bin` (application image)

You can flash these via USB using `esptool` or update over-the-air (OTA) via the app.

## Prerequisites
- Python installed (`python --version`)
- `esptool` installed:

```powershell
pip install esptool
```

- Identify your COM port (replace `COM5` below with yours). If the device doesn’t enter download mode automatically, hold BOOT and press RESET on the ESP32‑S3 XIAO Sense, then release BOOT.

## Method A — USB Flash (Prebuilt Binaries)

### Full Flash (bootloader + partitions + app)
Use this for a clean setup or when bootloader/partitions may be out of date.

```powershell
cd omiGlass/firmware/v2.3.1
python -m esptool --chip esp32s3 --port COM5 --baud 460800 write_flash `
  0x00000000 bootloader.bin `
  0x00008000 partitions.bin `
  0x00010000 firmware.bin `
  0x001D0000 firmware.bin
```