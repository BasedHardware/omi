# OMI Firmware Build and OTA Flash Guide

This guide provides step-by-step instructions for building the OMI firmware using nRF Connect SDK 2.9.0 and flashing it over-the-air (OTA) using the nRF Connect mobile app.

## Table of Contents
- [Prerequisites](#prerequisites)
- [Project Overview](#project-overview)
- [Environment Setup](#environment-setup)
- [Building the Firmware](#building-the-firmware)
- [OTA Flashing Process](#ota-flashing-process)
- [Build Outputs](#build-outputs)
- [Troubleshooting](#troubleshooting)
- [Technical Details](#technical-details)

## Prerequisites

### Hardware Requirements
- **Target Device**: OMI device with nRF5340 SoC (dual-core ARM Cortex-M33)
- **Mobile Device**: iOS or Android device with Bluetooth LE support
- **Development Machine**: macOS, Linux, or Windows

### Software Requirements
- **nRF Connect SDK**: Version 2.9.0
- **nrfutil**: Nordic's command-line utility
- **West**: Zephyr's meta-tool
- **CMake**: Version 3.20.0 or higher
- **Ninja**: Build system
- **Python**: 3.8+ with required packages
- **nRF Connect for Mobile**: iOS/Android app for OTA updates

## Project Overview

The OMI firmware is a dual-core nRF5340 application with the following features:

### Core Features
- **Audio Processing**: OPUS codec for real-time audio compression
- **Bluetooth LE**: MCUmgr-enabled for OTA updates
- **Microphone**: PDM microphone capture with processing
- **User Interface**: LED indicators, haptic feedback, button controls
- **Power Management**: Battery monitoring and charging support
- **Storage**: SD card support for offline audio storage

### Architecture
- **Application Core (Cortex-M33)**: Main application logic
- **Network Core (Cortex-M33)**: Bluetooth stack and radio management
- **Bootloader**: MCUboot for secure OTA updates
- **Partition Manager**: Static memory layout for dual-core operation

## Environment Setup

### 1. Install nRF Connect SDK 2.9.0

#### Using nrfutil (Recommended)
```bash
# Install nrfutil if not already installed
brew install nrfutil  # macOS
# or download from: https://www.nordicsemi.com/Products/Development-tools/nRF-Util

# Install toolchain manager
nrfutil install toolchain-manager

# Install nRF Connect SDK 2.9.0
nrfutil toolchain-manager install --ncs-version v2.9.0

# Verify installation
nrfutil toolchain-manager search
```

### 2. Install Build Dependencies

#### System Dependencies
```bash
# macOS
brew install ninja ccache

# Ubuntu/Debian
sudo apt install ninja-build ccache

# Windows
# Install via chocolatey or download binaries
```

#### Python Dependencies
The build process requires several Python packages. Install them in the West environment:

```bash
# Get the West Python path
WEST_PYTHON="/opt/homebrew/Cellar/west/1.4.0/libexec/bin/python"

# Install required packages
$WEST_PYTHON -m pip install cryptography intelhex ecdsa click cbor2
```

### 3. Initialize the nRF Connect SDK Workspace

If the `v2.9.0` directory doesn't exist or is empty, you need to initialize the nRF Connect SDK workspace:

```bash
# Navigate to the firmware directory
cd /path/to/omi/firmware

# Create and navigate to the v2.9.0 directory
mkdir -p v2.9.0
cd v2.9.0

# Initialize nRF Connect SDK v2.9.0 workspace
west init -m https://github.com/nrfconnect/sdk-nrf --mr v2.9.0

# Download all required repositories (this may take several minutes)
west update
```

**Note**: The `west update` command downloads approximately 1.5GB of source code including:
- Zephyr RTOS
- nRF Connect SDK modules
- MCUboot bootloader
- Various libraries and tools

If the workspace already exists and is properly configured, you can skip to step 4.

## Building the Firmware

### 1. Prepare Configuration Files

The project uses `omi.conf` but Zephyr expects `prj.conf`:

```bash
cd ../omi
cp omi.conf prj.conf
```

### 2. Build Command

From the West workspace directory (`v2.9.0`):

```bash
# Launch nRF Connect SDK environment and build
nrfutil toolchain-manager launch --ncs-version v2.9.0 --shell

# In the SDK environment:
west build -b omi/nrf5340/cpuapp ../omi --sysbuild -- -DBOARD_ROOT=/path/to/omi/firmware
```

### 3. Build Process Overview

The build system will:
1. **Configure MCUboot**: Set up the secure bootloader
2. **Build Network Core**: Compile the Bluetooth radio firmware (`ipc_radio`)
3. **Build Network Bootloader**: Compile the network core bootloader (`b0n`)
4. **Build Application**: Compile the main OMI application
5. **Sign Firmware**: Cryptographically sign all components
6. **Generate OTA Package**: Create `dfu_application.zip`

### 4. Build Output

Upon successful completion, you'll see:
```
Memory region         Used Size  Region Size  %age Used
           FLASH:      262908 B     982528 B     26.76%
             RAM:      244556 B       440 KB     54.28%
```

## Build Outputs

The build generates several important files in the `build/` directory:

### OTA Files
- **`dfu_application.zip`** (440 KB) - **Primary OTA package for nRF Connect app**
- `dfu_application.zip_manifest.json` - Package metadata

### Firmware Images
- `merged.hex` (869 KB) - Complete firmware for direct programming
- `signed_by_mcuboot_and_b0_ipc_radio.hex` - Signed application firmware
- `merged_CPUNET.hex` (533 KB) - Network core firmware

### Debug Files
- `build_info.yml` - Build configuration summary
- `partitions.yml` - Memory partition layout
- Individual component builds in subdirectories (`omi/`, `mcuboot/`, `ipc_radio/`, `b0n/`)

## OTA Flashing Process

### 1. Prepare the OTA Package

1. Locate `dfu_application.zip` in the `build/` directory
2. Transfer this file to your mobile device (email, cloud storage, etc.)

### 2. Install nRF Connect for Mobile

- **iOS**: Download from App Store
- **Android**: Download from Google Play Store

### 3. Flash via OTA

1. **Power on your OMI device** and ensure it's in range
2. **Open nRF Connect for Mobile**
3. **Scan for devices** - look for "Omi" in the device list
4. **Connect** to your OMI device
5. **Navigate to DFU tab** (Device Firmware Update)
6. **Select firmware file**:
   - Tap "Select file" or "Browse"
   - Choose `dfu_application.zip`
7. **Start update**:
   - Tap "Start" or "Upload"
   - Monitor progress (typically 2-5 minutes)
8. **Verify completion** - device will restart with new firmware

### 4. Update Process Details

During OTA update:
- **Stage 1**: Upload to secondary partition (~2-3 minutes)
- **Stage 2**: Verification and swap (automatic)
- **Stage 3**: Device restart with new firmware
- **Stage 4**: Confirmation of successful update

## Troubleshooting

### Build Issues

#### Missing Dependencies
```bash
# Error: ModuleNotFoundError: No module named 'cryptography'
/opt/homebrew/Cellar/west/1.4.0/libexec/bin/python -m pip install cryptography

# Error: ccache: command not found
brew install ccache

# Error: ninja: command not found
brew install ninja
```

#### Board Not Found
```bash
# Error: No board named 'omi' found
# Ensure BOARD_ROOT is set correctly:
west build -b omi/nrf5340/cpuapp ../omi --sysbuild -- -DBOARD_ROOT=/full/path/to/firmware
```

#### Configuration Issues
```bash
# Error: No prj.conf file found
cd ../omi
cp omi.conf prj.conf
```

#### Workspace Issues
```bash
# Error: No such file or directory: v2.9.0
# Initialize the workspace first:
cd /path/to/omi/firmware
mkdir -p v2.9.0 && cd v2.9.0
west init -m https://github.com/nrfconnect/sdk-nrf --mr v2.9.0
west update

# Error: already initialized in /path/to/omi/firmware
# Remove broken workspace and reinitialize:
rm -rf .west
cd v2.9.0
west init -m https://github.com/nrfconnect/sdk-nrf --mr v2.9.0
west update
```

### OTA Flashing Issues

#### Device Not Found
- Ensure OMI device is powered on and in range
- Check Bluetooth is enabled on mobile device
- Try restarting both devices

#### Update Fails
- Verify `dfu_application.zip` file integrity
- Ensure sufficient battery level on OMI device
- Try updating in smaller chunks (app may have options)

#### Connection Issues
- Move closer to the device
- Ensure no other apps are connected to the OMI
- Restart the nRF Connect app

## Technical Details

### Memory Layout
```
Application Core (nRF5340 CPUAPP):
├── MCUboot Bootloader (64 KB)
├── Application Primary (982 KB)
├── Application Secondary (982 KB) - OTA staging
└── Settings/NVS

Network Core (nRF5340 CPUNET):
├── Network Bootloader (34 KB)
├── Network Primary (222 KB)
└── Network Secondary (222 KB) - OTA staging
```

### Security Features
- **RSA-2048 Signing**: All firmware images are cryptographically signed
- **Secure Boot**: MCUboot verifies signatures before execution
- **Rollback Protection**: Prevents downgrade to vulnerable versions
- **Encrypted Communication**: MCUmgr uses encrypted BLE transport

### Build Configuration Highlights
```
CONFIG_NCS_SAMPLE_MCUMGR_BT_OTA_DFU=y    # Enable OTA updates
CONFIG_BT_PERIPHERAL=y                    # Bluetooth peripheral role
CONFIG_MCUMGR_GRP_IMG_ALLOW_ERASE_PENDING=y  # Allow image management
CONFIG_OMI_CODEC_OPUS=y                   # Enable OPUS codec
CONFIG_BOOTLOADER_MCUBOOT=y               # Use MCUboot
```

### Firmware Features
- **Audio Codec**: OPUS 1.2.1 for efficient audio compression
- **Bluetooth**: BLE 5.0 with extended advertising and 2M PHY
- **Power Management**: Advanced power states and battery monitoring
- **File System**: EXT2 support for SD card storage
- **Sensors**: LSM6DSL accelerometer/gyroscope support

## Success Indicators

### Build Success
```
[24/24] Generating ../dfu_application.zip
-- west build: finished
```

### OTA Success
- nRF Connect app shows "Update completed successfully"
- OMI device restarts and functions normally
- New firmware version is active

---

## Additional Resources

- [nRF Connect SDK Documentation](https://developer.nordicsemi.com/nRF_Connect_SDK/doc/latest/)
- [MCUboot Documentation](https://docs.mcuboot.com/)
- [nRF Connect for Mobile](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-mobile)
- [OMI Hardware Documentation](https://docs.omi.me/)

---

**Last Updated**: August 2024  
**SDK Version**: nRF Connect SDK 2.9.0  
**Target Hardware**: OMI nRF5340 Device
