# Flashing Instructions for Omi Firmware v3.0.7

This guide provides step-by-step instructions for flashing the Omi firmware using J-Link on both macOS and Windows systems.

## Prerequisites

- Omi device connected via USB
- J-Link software installed (see installation instructions below)
- Appropriate USB drivers for your device

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
- The device should now be running firmware version 3.0.7

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

### Getting Help

If you encounter issues:
- Check the J-Link software documentation
- Ensure your device is properly connected and recognized
- Verify you're using the correct `.jlink` scripts for your platform

---

**Note**: Always flash the network core before the application core to ensure proper functionality.
