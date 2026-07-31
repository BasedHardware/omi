# Device SDK parity matrix

| Capability | Python | Swift | React Native | TS device | Go | Rust | Dart | C++ |
|------------|--------|-------|--------------|-----------|----|------|------|-----|
| BLE UUIDs / packet strip | yes | yes | yes | yes | yes | yes | yes (app models.dart) | yes |
| Full BLE scan/connect/listen | yes (bleak) | yes (CoreBluetooth) | yes (ble-plx) | optional `@stoprocent/noble` | `-tags ble` tinygo bluetooth | feature `ble` btleplug | **flutter_blue_plus** (app UUID map) | `OMI_DEVICE_BLE` SimpleBLE |
| Audio notify + header strip | yes | yes | yes | yes | yes | yes | yes | yes |
| Read codec / battery | yes | yes | yes | partial | codec yes | via chars | yes (app parity) | via SimpleBLE |
| STT Deepgram | yes | yes | yes | yes | yes | feature | yes | URL helper |
| STT Whisper | optional/runner | SwiftWhisper | runner | runner | runner | feature | runner | macro |
| STT Parakeet `/v3/stream` | yes | yes | yes | yes | yes | feature | yes | URL helper |

PCM contract for STT: **16-bit LE mono @ 16 kHz**.

## Dart BLE note

Production Omi app uses **native Pigeon BLE**. The Dart device SDK uses **flutter_blue_plus** with the same GATT UUIDs and audio/codec/battery flows from:

- `app/lib/services/devices/models.dart`
- `app/lib/services/devices/connectors/omi_connection.dart`
