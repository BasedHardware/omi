# Flashing Instructions for Omi Firmware v3.0.8

> ⚠️ **Stale bundle (added 2026-10):** the `.hex` files shipped in this folder are
> firmware **3.0.8**, many releases behind the current `Omi_CV1_v3.0.x` releases.
> Always download the current `Omi_CV1_v<ver>.hex` / `Omi_CV1_v<ver>_CPUNET.hex`
> from
> [GitHub Releases](https://github.com/BasedHardware/omi/releases?q=release_firmware+OMI+CV1)
> and replace the files below before flashing — the scripts expect the exact
> names `merged.hex` and `merged_CPUNET.hex`. For OTA updates, prefer the app
> (Settings → Device Settings → Product Update) with `Omi_CV1_OTA_v<ver>.zip`.

This guide provides step-by-step instructions for flashing the Omi firmware using J-Link on both macOS and Windows systems.

## Prerequisites

- Omi CV1 device with a SWD programming connection (J-Link + the Omi flash cable; the pendant has no USB port — the magnetic charger carries power only, not data)
- J-Link software installed (see installation instructions below)
- Appropriate USB drivers for the J-Link (the pendant itself has no USB port)
- Latest firmware files downloaded from GitHub releases

## Important: Update Firmware Files Before Flashing

⚠️ **Critical Step**: Before flashing, you must replace the existing firmware files with the latest versions from GitHub releases.

### Step 1: Download Latest Firmware

1. Go to the [Omi GitHub Releases page](https://github.com/BasedHardware/omi/releases)
2. Find the latest release version
3. Download the following files from the latest `Omi_CV1_v<ver>` release:
   - `Omi_CV1_v<ver>.hex` - Application core firmware
   - `Omi_CV1_v<ver>_CPUNET.hex` - Network core firmware

   The J-Link scripts in this folder `loadfile merged.hex` / `merged_CPUNET.hex`,
   so save the downloads under those exact names (Step 2 below).

### Step 2: Replace Existing Firmware Files

**For macOS:**
1. Navigate to the `MAC/` folder in your FLASH_3.0.8 directory
2. **Backup existing files** (optional but recommended):
   ```bash
   mv merged.hex merged.hex.backup
   mv merged_CPUNET.hex merged_CPUNET.hex.backup
   ```
3. **Replace with downloaded files**:
   - Copy the downloaded `Omi_CV1_v<ver>.hex` into `MAC/` as `merged.hex`
   - Copy the downloaded `Omi_CV1_v<ver>_CPUNET.hex` into `MAC/` as `merged_CPUNET.hex`

**For Windows:**
1. Navigate to the `WINDOWS\` folder in your FLASH_3.0.8 directory
2. **Backup existing files** (optional but recommended):
   - Rename `merged.hex` to `merged.hex.backup`
   - Rename `merged_CPUNET.hex` to `merged_CPUNET.hex.backup`
3. **Replace with downloaded files**:
   - Copy the downloaded `Omi_CV1_v<ver>.hex` into `WINDOWS\` as `merged.hex`
   - Copy the downloaded `Omi_CV1_v<ver>_CPUNET.hex` into `WINDOWS\` as `merged_CPUNET.hex`

### Step 3: Verify File Replacement

Ensure that:
- The new `merged.hex` and `merged_CPUNET.hex` files are in the correct platform folder
- The file sizes match the downloaded files (they should be different from the original files)
- The modification dates reflect when you copied them

## macOS Instructions

### 1. Install J-Link Software

1. Download J-Link software from [SEGGER's official website](https://www.segger.com/downloads/jlink/)
2. Install the downloaded package following the standard macOS installation process
3. The J-Link tools will be automatically added to your system PATH

### 2. Navigate to MAC Folder

```bash
cd MAC
```

### 3. Flash the Firmware

Run these commands **one by one** to flash each core:

```bash
# Flash the network core first
JLinkExe -CommanderScript program_net.jlink

# Then flash the application core
JLinkExe -CommanderScript program_app.jlink
```

## Windows Instructions

### 1. Install J-Link Software

1. Download J-Link software from [SEGGER's official website](https://www.segger.com/downloads/jlink/)
2. Install the downloaded executable
3. **Important**: Add J-Link to your system PATH:
   - Right-click "This PC" → Properties → Advanced System Settings
   - Click "Environment Variables"
   - Under "System Variables", find and select "Path", then click "Edit"
   - Click "New" and add the J-Link installation path
   - Default path is usually: `C:\Program Files\SEGGER\JLink\`
   - Click "OK" to save changes

### 2. Navigate to WINDOWS Folder

```cmd
cd WINDOWS
```

### 3. Flash the Firmware

Run these commands **one by one** to flash each core:

```cmd
# Flash the network core first
JLink.exe -CommanderScript program_net.jlink

# Then flash the application core
JLink.exe -CommanderScript program_app.jlink
```

## Verification

After completing the flashing process:

- **Success Indicator**: If the LEDs start blinking, you have successfully flashed the board! 🎉
- The device should now be running the latest firmware version you downloaded from GitHub releases
- You can verify the firmware version through the Omi app or device interface

## Troubleshooting

### Common Issues

1. **"JLinkExe/JLink.exe not found"**
   - Ensure J-Link software is properly installed
   - On Windows, verify the PATH environment variable is correctly set
   - Try restarting your terminal/command prompt

2. **Connection Issues**
   - Check USB cable connection
   - Ensure device is in programming mode
   - Try a different USB port

3. **Flashing Fails**
   - Make sure to flash the network core (`program_net.jlink`) first
   - Wait for each command to complete before running the next one
   - Check that no other applications are using the device
   - Verify you have the latest firmware files from GitHub releases

4. **Firmware File Issues**
   - Ensure `merged.hex` and `merged_CPUNET.hex` are the latest versions from GitHub releases
   - Check that file sizes are reasonable (typically several hundred KB to a few MB)
   - Verify files are not corrupted by re-downloading if necessary
   - Make sure files are in the correct platform folder (MAC/ or WINDOWS/)

### Getting Help

If you encounter issues:
- Check the J-Link software documentation
- Ensure your device is properly connected and recognized
- Verify you're using the correct `.jlink` scripts for your platform

---

**Note**: Always flash the network core before the application core to ensure proper functionality.
