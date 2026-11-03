library;

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/utils/omi_glass_protocol.dart';

BtDevice _omiDevice({required String name, bool? omiRenamable}) => BtDevice(
      id: 'aa:bb:cc:dd:ee:01',
      name: name,
      type: DeviceType.omi,
      rssi: -40,
      omiRenamable: omiRenamable,
      locator: DeviceLocator.bluetooth(deviceId: 'aa:bb:cc:dd:ee:01'),
    );

void main() {
  test('renamable Omi CV1 is not classified as OmiGlass when the name contains glass', () {
    final device = _omiDevice(name: 'Kitchen Glass Omi', omiRenamable: true);

    expect(OmiGlassProtocol.usesOmiGlassProtocol(device), isFalse);
    expect(DeviceConnectionFactory.create(device), isA<OmiDeviceConnection>());
  });

  test('legacy Omi without rename feature still uses the name heuristic', () {
    final device = _omiDevice(name: 'OmiGlass Dev', omiRenamable: false);

    expect(OmiGlassProtocol.usesOmiGlassProtocol(device), isTrue);
  });
}
