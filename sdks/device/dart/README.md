# omi_device (Dart)

Shared Omi device BLE constants, packet framing, STT helpers, and optional
`flutter_blue_plus` client for Flutter apps.

```dart
import 'package:omi_device/omi_device.dart';
import 'package:omi_device/ble/omi_ble.dart';

final payload = stripPacketHeader(rawNotifyBytes);

final ble = FlutterBluePlusOmiBle();
final devices = await ble.scan();
await ble.connect(devices.first.id);
await ble.listenPayload((p) { /* codec payload */ });
await ble.disconnect();
```

Protocol constants stay pure-Dart (`stripPacketHeader`, UUIDs). BLE client needs
Flutter + `flutter_blue_plus`.
