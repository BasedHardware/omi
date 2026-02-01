# Firmware Components Reference

Quick reference guide to firmware architecture for Omi devices.

## Device Types

### Omi Device
**Location**: `omi/`
**Platform**: nRF chips (nRF52840, nRF5340)
**RTOS**: Zephyr

### Omi Glass
**Location**: `omiGlass/`
**Platform**: ESP32-S3
**Framework**: Arduino/ESP-IDF

## Omi Device Firmware (`omi/`)

### Architecture

**Main Components**:
- BLE services implementation
- Audio capture and encoding
- Battery management
- Device information service

### BLE Services

#### Audio Streaming Service
**UUID**: `19B10000-E8F2-537E-4F6C-D104768A1214`

**Characteristics**:
- **Audio Data** (`19B10001-E8F2-537E-4F6C-D104768A1214`): Audio stream to app
- **Codec Type** (`19B10002-E8F2-537E-4F6C-D104768A1214`): Codec identifier

**Supported Codecs**:
- `0`: PCM 16-bit, 16 kHz, mono
- `1`: PCM 16-bit, 8 kHz, mono
- `10`: Mu-law, 16 kHz, 8-bit mono
- `11`: Mu-law, 8 kHz, 8-bit mono
- `20`: Opus, 16 kHz, 16-bit mono (default since v1.0.3)

#### Battery Service
**UUID**: `0x180F` (standard BLE Battery Service)

**Characteristics**:
- **Battery Level** (`0x2A19`): Battery percentage
- **Notifications**: Supported since firmware v1.5

#### Device Information Service
**UUID**: `0x180A` (standard BLE Device Information Service)

**Characteristics**:
- **Manufacturer Name** (`0x2A29`): "Based Hardware"
- **Model Number** (`0x2A24`): "Omi"
- **Hardware Revision** (`0x2A27`): "Seeed Xiao BLE Sense"
- **Firmware Revision** (`0x2A26`): Firmware version (e.g., "1.0.3")

**Available since**: Firmware v1.0.3

### Audio Packet Format

**Header** (3 bytes):
- Bytes 0-1: Packet number (little-endian, 0-65535)
- Byte 2: Index (position within packet)

**Payload**:
- 160 audio samples per packet
- Format depends on codec type
- Little-endian byte order

**Fragmentation**:
- If packet exceeds BLE MTU - 3 bytes, split across multiple notifications
- Example: 320-byte PCM packet on iOS → 2 notifications (251 + 75 bytes)

### Key Directories

#### `firmware/`
Main firmware source code:
- BLE service implementation
- Audio processing
- Codec encoding (Opus, PCM, Mu-law)
- Power management
- Device configuration

#### `hardware/`
Hardware design files:
- PCB designs
- Schematics
- 3D models
- Assembly guides

### Build System

**Zephyr RTOS**:
- Configuration files (`.conf`)
- Device tree definitions
- Kconfig options

**Build Commands**:
- See `omi/firmware/BUILD_AND_OTA_FLASH.md`
- OTA (Over-The-Air) update support

## Omi Glass Firmware (`omiGlass/`)

### Architecture

**Platform**: ESP32-S3
**Framework**: Arduino/ESP-IDF

**Key Features**:
- BLE audio streaming
- Camera integration (ESP32-CAM)
- Display control
- Power management

### BLE Services

Similar structure to Omi device:
- Audio streaming service
- Battery service
- Device information service

### Camera Integration

**Features**:
- Photo capture
- Video streaming (if supported)
- Image processing

## Firmware Versions

### Version History

- **v1.0.3+**: Device Information Service added, Opus codec default
- **v1.5+**: Battery notifications supported

### Version Checking

Firmware version available via Device Information Service:
- Read `0x2A26` (Firmware Revision) characteristic
- Returns version string (e.g., "1.0.3")

## Development Workflow

### Building Firmware

1. Set up Zephyr/ESP-IDF environment
2. Configure device tree and Kconfig
3. Build firmware image
4. Flash to device

### OTA Updates

**Location**: `backend/routers/firmware.py`

**Process**:
1. Backend hosts firmware binaries
2. App checks for updates
3. Downloads firmware via API
4. Transfers to device via BLE
5. Device applies update

## Protocol Reference

**BLE Protocol**: See `docs/doc/developer/Protocol.mdx`

**Key Points**:
- Device discovered by name "Omi"
- Audio data sent as BLE notifications
- 3-byte header on each packet
- Codec negotiated via Codec Type characteristic
- Little-endian byte order

## Testing

### Device Testing
- BLE connection testing
- Audio quality verification
- Battery life testing
- Codec compatibility

### Integration Testing
- App-to-device communication
- Audio streaming quality
- Firmware update process

## Related Documentation

- Protocol: `docs/doc/developer/Protocol.mdx`
- Hardware Assembly: `docs/doc/assembly/Build_the_device.mdx`
- Flashing: `docs/doc/get_started/Flash_device.mdx`
- Architecture: `.cursor/ARCHITECTURE.md`
