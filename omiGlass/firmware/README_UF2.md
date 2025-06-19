# OMI Glass UF2 Firmware Builder

This directory contains tools to build and flash OMI Glass firmware using the UF2 (USB Flashing Format) method, which is the **easiest way** to flash your ESP32-S3 device.

## 🚀 Quick Start

### 1. Build UF2 File
```bash
# Build optimized release version (recommended)
./build_uf2.sh -e uf2_release

# Or build standard version
./build_uf2.sh
```

### 2. Flash to Device
1. **Enter Bootloader Mode:**
   - Hold down the **BOOT** button on your ESP32-S3
   - While holding BOOT, press and release the **RESET** button
   - Release the **BOOT** button
   - Your device should appear as a USB drive named **"ESP32S3"**

2. **Flash the Firmware:**
   - Copy `omi_glass_firmware.uf2` to the ESP32S3 drive
   - The device will automatically flash and reboot

3. **Monitor (Optional):**
   ```bash
   pio device monitor --baud 115200
   ```

## 📋 Available Build Scripts

### Shell Script (Recommended)
```bash
./build_uf2.sh [OPTIONS]

Options:
  -e, --env ENV        Build environment (seeed_xiao_esp32s3, uf2_release)
  -c, --convert-only   Only convert existing binary to UF2
  -b, --binary FILE    Convert specific binary file
  -o, --output FILE    Custom output filename
  -h, --help          Show help
```

### Python Script (Advanced)
```bash
python3 build_uf2.py [OPTIONS]

# Same options as shell script
# More detailed output and error handling
```

## 🏗️ Build Environments

| Environment | Description | Use Case |
|-------------|-------------|----------|
| `seeed_xiao_esp32s3` | Standard build | Development |
| `seeed_xiao_esp32s3_slow` | Slower upload | Connection issues |
| `uf2_release` | Optimized release | Production |

## 📁 Generated Files

After building, you'll get:
- `omi_glass_firmware.uf2` - Main firmware file (ready to flash)
- `FLASHING_INSTRUCTIONS.md` - Detailed flashing guide
- `.pio/build/*/firmware.bin` - Original binary (for advanced use)

## ⚡ Automatic UF2 Generation

The build system automatically generates UF2 files when using PlatformIO:
```bash
# These commands will also create UF2 files automatically
pio run -e seeed_xiao_esp32s3
pio run -e uf2_release
```

## 🔧 Alternative Flashing Methods

### Method 1: UF2 (Easiest)
- Drag and drop flashing
- No drivers needed
- Works on all platforms

### Method 2: PlatformIO
```bash
pio run -t upload
```

### Method 3: esptool
```bash
esptool.py --chip esp32s3 --port /dev/ttyUSB0 write_flash 0x10000 firmware.bin
```

### Method 4: Existing Scripts
```bash
./build_and_test.sh upload
./detect_and_upload.sh
```

## 📊 Firmware Features

✅ **Camera:** 30-second interval photos (VGA quality)  
✅ **Battery:** Dual 500mAh monitoring with protection  
✅ **BLE:** OMI protocol compliant communication  
✅ **Power:** 8+ hour battery life with optimization  
✅ **Audio:** Real-time streaming support (ready for future)  

## 🛠️ Troubleshooting

### Device Not Appearing as USB Drive
1. Make sure you're in bootloader mode (hold BOOT + press RESET)
2. Try a different USB cable
3. Connect directly to computer (not through hub)
4. Check if device drivers are installed

### Build Fails
1. Make sure PlatformIO is installed: `pip install platformio`
2. Try: `pio run --target clean` then rebuild
3. Check that all dependencies are installed

### Upload Issues
1. Try the slower environment: `./build_uf2.sh -e seeed_xiao_esp32s3_slow`
2. Use traditional upload: `pio run -t upload`
3. Put device in bootloader mode and try again

### Firmware Not Working
1. Check serial monitor: `pio device monitor --baud 115200`
2. Verify LED boot sequence (5 quick blinks)
3. Check battery connections and voltage
4. Ensure camera is properly connected

## 📝 File Sizes

Typical build sizes:
- **Binary:** ~950 KB
- **UF2:** ~1.9 MB (double size due to UF2 format)
- **Memory Usage:** ~60% flash, ~30% RAM

## 🔍 Monitoring

After flashing, monitor the device:
```bash
pio device monitor --baud 115200
```

Expected output:
```
Setup started...
BLE initialized and advertising started.
Camera initialized successfully.
Battery: 4.15V (95%)
Default capture interval set to 30 seconds.
Setup complete.
```

## 📚 Additional Resources

- **Main Documentation:** `README_PRODUCTION.md`
- **PlatformIO Guide:** `README_PLATFORMIO.md`  
- **Battery Setup:** `BATTERY_SETUP.md`
- **Build Scripts:** `build_and_test.sh`

## 🎯 Quick Reference Commands

```bash
# Build release UF2
./build_uf2.sh -e uf2_release

# Convert existing binary
./build_uf2.sh -c -b path/to/firmware.bin

# Monitor device
pio device monitor --baud 115200

# Traditional upload
pio run -t upload

# Clean build
pio run --target clean
```

## 💡 Pro Tips

1. **Use release build** (`uf2_release`) for best battery life
2. **Monitor during first flash** to verify everything works
3. **Keep UF2 files** for easy reflashing
4. **Test bootloader mode** before building if unsure
5. **Use slower environment** if having connection issues

---

🎉 **Happy flashing!** The UF2 method makes firmware updates as easy as copying a file. 