# Omi Device SDKs (multi-language)

Portable **device BLE protocol** helpers for languages that do not yet have a full native BLE stack package.

## Already-complete full device SDKs

| Path | Platform | Notes |
|------|----------|-------|
| [`../python`](../python) | Desktop Python | bleak scan/listen + Opus decode + Deepgram |
| [`../swift`](../swift) | iOS/macOS | CoreBluetooth + codecs + Whisper |
| [`../react-native`](../react-native) | iOS/Android | react-native-ble-plx |

## New portable protocol packages

| Lang | Path | What you get |
|------|------|----------------|
| TypeScript | [`typescript/`](typescript/) | UUIDs, header strip, transport interface |
| Go | [`go/`](go/) | UUIDs + `StripPacketHeader` + optional BLE (`-tags ble`, tinygo bluetooth) |
| Rust | [`rust/`](rust/) | UUIDs + `strip_packet_header` |
| C++ | [`cpp/`](cpp/) | UUIDs + `StripPacketHeader` |
| Dart | [`dart/`](dart/) | UUIDs + `stripPacketHeader` |

Protocol source of truth: [`PROTOCOL.md`](PROTOCOL.md).

### Why not full BLE clients in every language?

BLE stacks are OS-specific (`CoreBluetooth`, `bluer`/`btleplug`, `WinRT`, `Web Bluetooth`, `noble`). Shipping a production scanner in each language is a large ongoing surface. These packages share the **Omi packet/GATT contract** so native BLE code stays thin.

Full connect/listen loops remain in Python/Swift/RN (and the Flutter app). Wire your platform BLE library to `AUDIO_DATA_UUID` and strip headers with these helpers.

### Opus decode

Python uses `opuslib`. Other languages should use the platform Opus decoder (libopus / `audiopus` / Flutter plugins). Header strip is identical everywhere.

## STT engines

See [`STT.md`](STT.md) and [`PARITY.md`](PARITY.md).

All languages expose the same engine names: `deepgram`, `whisper`, `parakeet`.

## BLE backends (real libraries)

| Lang | Library | Gate |
|------|---------|------|
| Python | bleak | always |
| Swift | CoreBluetooth | always |
| React Native | react-native-ble-plx | peer |
| TypeScript | @stoprocent/noble | optionalDependency |
| Go | tinygo.org/x/bluetooth | `-tags ble` |
| Rust | btleplug | feature `ble` |
| Dart | flutter_blue_plus (app UUID map) | Flutter package |
| C++ | SimpleBLE | `-DOMI_DEVICE_BLE=ON` |
