# omi_device (Dart / Flutter)

Portable Omi **device** SDK for Flutter:

- GATT UUID map from the main app (`app/lib/services/devices/models.dart`)
- BLE via **flutter_blue_plus** (`FlutterBluePlusOmiBle`) — scan / connect / audio notify / codec / battery
- Packet header strip (3 bytes)
- STT engines: deepgram / whisper / parakeet

## BLE quickstart

```dart
import 'package:omi_device/omi_device.dart';

final ble = createOmiBleClient(); // FlutterBluePlusOmiBle
final devices = await ble.scan(timeout: const Duration(seconds: 8));
await ble.connect(devices.first.id);

// Raw packets (with 3-byte header) or stripped payload:
ble.audioPackets().listen((packet) { /* opus frames */ });
ble.audioPayloads().listen((payload) { /* after stripPacketHeader */ });

final codec = await ble.readCodec();
final battery = await ble.readBatteryLevel();
```

Note: the production Omi app uses **native Pigeon BLE** for lifecycle. This package uses FBP so third-party apps can integrate without the full app binary.

## STT

See `sdks/device/STT.md`.

`ParakeetTranscriber` drops PCM until the server sends `ready`. If the server closes the stream before
`ready` (for example 1013 `capacity_full` or `service_not_ready`), `appendPcm` and `stop` throw an
`SttStreamClosedException` carrying the close code and reason, so callers can retry or switch engines.

## Tests

Run `flutter test` in this directory. The STT tests drive the transcribers through an in-memory WebSocket
channel, so the suite needs no device, credentials, or transcription service. CI runs it for changes under
`sdks/device/dart/` (`.github/workflows/sdk-dart.yml`).
