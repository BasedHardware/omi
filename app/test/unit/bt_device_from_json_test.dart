import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';

void main() {
  group('BtDevice.fromJson', () {
    test('parses a well-formed json round-trip', () {
      final device = BtDevice(id: 'AA:BB:CC', name: 'Omi', type: DeviceType.omi, rssi: -60);
      final restored = BtDevice.fromJson(device.toJson());
      expect(restored.id, 'AA:BB:CC');
      expect(restored.name, 'Omi');
      expect(restored.type, DeviceType.omi);
      expect(restored.rssi, -60);
    });

    // Regression: Crashlytics f47896e23d3d0823 — persisted rssi stored as a
    // String crashed fromJson with "type 'String' is not a subtype of type 'int'".
    test('does not throw when rssi is persisted as a String', () {
      final restored = BtDevice.fromJson({'name': 'Omi', 'id': 'AA:BB:CC', 'type': 'omi', 'rssi': '-60'});
      expect(restored.rssi, -60);
    });

    test('falls back to safe defaults for missing or mistyped fields', () {
      final restored = BtDevice.fromJson({
        'name': null,
        'id': 42,
        'type': 'omi',
        'rssi': 'garbage',
        'locator': 'not-a-map',
        'modelNumber': 1,
      });
      expect(restored.name, '');
      expect(restored.id, '');
      expect(restored.rssi, 0);
      expect(restored.locator, isNull);
      expect(restored.modelNumber, 'Unknown');
    });
  });
}
