import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';

void main() {
  test('the PLAUD pairing note does not promise compatibility Omi cannot check', () {
    // Omi has no PLAUD firmware read: the version it shows is a 1.0.0 placeholder. A NotePin on
    // PLAUD firmware 2.2 paired, saw "current firmware works great with Omi", and never recorded.
    final device = BtDevice(name: 'PLAUD NotePin', id: 'plaud-1', type: DeviceType.plaud, rssi: -50);

    final message = device.getFirmwareWarningMessage();

    expect(message, isNot(contains('works great')));
    expect(message, contains('may not be supported'));
    expect(device.getFirmwareWarningTitle(), 'Compatibility Note');
  });
}
