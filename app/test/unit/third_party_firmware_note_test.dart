import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';

void main() {
  // Omi has no firmware compatibility check for these devices: when one answers no Device Information
  // request its version is a 1.0.0 placeholder. A NotePin on PLAUD firmware 2.2 paired, saw "current
  // firmware works great with Omi", and never recorded.
  for (final (type, vendorApp) in [
    (DeviceType.plaud, 'PLAUD'),
    (DeviceType.fieldy, 'Compass'),
    (DeviceType.friendPendant, 'Friend'),
    (DeviceType.limitless, 'Limitless'),
  ]) {
    test('the ${type.name} pairing note does not promise compatibility Omi cannot check', () {
      final device = BtDevice(name: 'Test device', id: 'id-1', type: type, rssi: -50);

      final message = device.getFirmwareWarningMessage();

      expect(message, isNot(contains('works great')));
      expect(message, contains('may not be supported'));
      expect(message, contains('$vendorApp app'));
      expect(device.getFirmwareWarningTitle(), 'Compatibility Note');
      // A "Don't show again" given to the old note must not hide this one.
      expect(device.firmwareWarningAcknowledgedKey, isNot('firmware_warning_acknowledged_DeviceType.${type.name}'));
    });
  }

  test("Bee keeps its acknowledgment key: its note's wording did not change", () {
    final bee = BtDevice(name: 'Bee', id: 'bee-1', type: DeviceType.bee, rssi: -50);
    expect(bee.firmwareWarningAcknowledgedKey, 'firmware_warning_acknowledged_DeviceType.bee');
  });
}
