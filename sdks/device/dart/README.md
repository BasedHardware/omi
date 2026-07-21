# omi_device (Dart)

Shared Omi device BLE constants + packet framing for Flutter.

Full mobile BLE UX still lives in the Omi Flutter app; this package is the portable protocol layer.

```dart
import 'package:omi_device/omi_device.dart';

final payload = stripPacketHeader(rawNotifyBytes);
```
