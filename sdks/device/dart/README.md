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
