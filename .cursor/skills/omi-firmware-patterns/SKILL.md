---
name: omi-firmware-patterns
description: "Firmware C C++ BLE services audio codecs Opus PCM Mu-law nRF ESP32 Zephyr Arduino embedded systems"
---

# Omi Firmware Patterns Skill

This skill provides guidance for working with Omi firmware, including BLE services, audio codecs, and device communication.

## When to Use

Use this skill when:
- Working on firmware code in `omi/` or `omiGlass/`
- Implementing BLE services
- Working with audio codecs (Opus, PCM, Mu-law)
- Debugging device communication issues

## Key Patterns

### BLE Services

#### Audio Streaming Service

**UUID**: `19B10000-E8F2-537E-4F6C-D104768A1214`

**Characteristics**:
- Audio Data: `19B10001-E8F2-537E-4F6C-D104768A1214`
- Codec Type: `19B10002-E8F2-537E-4F6C-D104768A1214`

#### Standard Services

- **Battery Service**: `0x180F` (standard)
- **Device Information Service**: `0x180A` (standard)

### Audio Packet Format

**Header** (3 bytes):
- Bytes 0-1: Packet number (little-endian, 0-65535)
- Byte 2: Index (position within packet)

**Payload**:
- 160 audio samples per packet
- Format depends on codec type

**Fragmentation**: If packet exceeds BLE MTU - 3 bytes, split across multiple notifications

### Codec Types

- `0`: PCM 16-bit, 16 kHz, mono
- `1`: PCM 16-bit, 8 kHz, mono
- `10`: Mu-law, 16 kHz, 8-bit mono
- `11`: Mu-law, 8 kHz, 8-bit mono
- `20`: Opus, 16 kHz, 16-bit mono (default since v1.0.3)

### Zephyr RTOS (Omi Device)

#### BLE Service Definition

```c
BT_GATT_SERVICE_DEFINE(audio_svc,
    BT_GATT_PRIMARY_SERVICE(BT_UUID_AUDIO_SERVICE),
    BT_GATT_CHARACTERISTIC(BT_UUID_AUDIO_DATA,
        BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
        BT_GATT_PERM_READ,
        read_audio_data, NULL, NULL),
);
```

#### Audio Packet Sending

```c
void send_audio_packet(audio_packet_t *packet) {
    uint8_t buffer[3 + sizeof(packet->audio_data)];
    
    // Header
    buffer[0] = packet->packet_number & 0xFF;
    buffer[1] = (packet->packet_number >> 8) & 0xFF;
    buffer[2] = packet->index;
    
    // Audio data
    memcpy(&buffer[3], packet->audio_data, sizeof(packet->audio_data));
    
    // Send via BLE notification
    bt_gatt_notify(conn, &audio_char, buffer, sizeof(buffer));
}
```

### ESP32-S3 (Omi Glass)

#### Arduino Framework

```cpp
BLEService *pService = pServer->createService(SERVICE_UUID);
BLECharacteristic *pChar = pService->createCharacteristic(
    AUDIO_DATA_UUID,
    BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
);
```

## Common Tasks

### Adding a New BLE Characteristic

1. Define UUID
2. Add to service definition
3. Implement read/write/notify callbacks
4. Handle data format correctly

### Implementing Audio Codec

1. Initialize codec encoder
2. Encode audio samples
3. Format as packet with header
4. Send via BLE notification

### Debugging BLE Issues

1. Check service/characteristic UUIDs
2. Verify packet format (header + payload)
3. Check MTU size and fragmentation
4. Verify codec type negotiation

## Related Documentation

**The `docs/` folder is the single source of truth for all user-facing documentation, deployed at [docs.omi.me](https://docs.omi.me/).**

- **BLE Protocol**: `docs/doc/developer/Protocol.mdx` - [View online](https://docs.omi.me/doc/developer/Protocol)
- **Firmware Compilation**: `docs/doc/developer/firmware/Compile_firmware.mdx` - [View online](https://docs.omi.me/doc/developer/firmware/Compile_firmware)
- **Hardware Docs**: `docs/doc/hardware/` - [View online](https://docs.omi.me/doc/hardware/)
- **Firmware Architecture**: `.cursor/rules/firmware-architecture.mdc`

## Related Cursor Resources

### Rules
- `.cursor/rules/firmware-architecture.mdc` - Firmware system architecture
- `.cursor/rules/firmware-ble-service.mdc` - BLE service implementation
- `.cursor/rules/firmware-audio-codecs.mdc` - Audio codec implementation
- `.cursor/rules/flutter-ble-protocol.mdc` - Flutter BLE integration

### Subagents
- `.cursor/agents/firmware-engineer/` - Uses this skill for firmware development
- `.cursor/agents/flutter-developer/` - Uses this skill for BLE integration

### Commands
- `/flutter-setup` - Uses this skill for firmware setup
