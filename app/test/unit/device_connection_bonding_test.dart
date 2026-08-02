import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/transports/native_ble_transport.dart';

void main() {
  group('DeviceConnectionFactory bonding', () {
    test('Omi and Limitless BLE transports require bonding', () {
      for (final type in [DeviceType.omi, DeviceType.limitless]) {
        final device = BtDevice(
          id: 'AA:BB:CC:DD:EE:FF',
          name: type.name,
          type: type,
          rssi: -60,
          locator: DeviceLocator.bluetooth(deviceId: 'AA:BB:CC:DD:EE:FF'),
        );

        final connection = DeviceConnectionFactory.create(device);
        expect(connection, isNotNull);

        final transport = connection!.transport;
        expect(transport, isA<NativeBleTransport>());
        expect((transport as NativeBleTransport).requiresBond, isTrue);
      }
    });

    test('other BLE device types do not require bonding by default', () {
      final device = BtDevice(
        id: 'AA:BB:CC:DD:EE:FF',
        name: 'Bee',
        type: DeviceType.bee,
        rssi: -60,
        locator: DeviceLocator.bluetooth(deviceId: 'AA:BB:CC:DD:EE:FF'),
      );

      final connection = DeviceConnectionFactory.create(device);
      expect(connection, isNotNull);
      expect((connection!.transport as NativeBleTransport).requiresBond, isFalse);
    });

    test('name-detected OmiGlass does not require bonding even when typed as omi', () {
      final device = BtDevice(
        id: 'AA:BB:CC:DD:EE:FF',
        name: 'Omi Glass',
        type: DeviceType.omi,
        rssi: -60,
        locator: DeviceLocator.bluetooth(deviceId: 'AA:BB:CC:DD:EE:FF'),
      );

      final connection = DeviceConnectionFactory.create(device);
      expect(connection, isNotNull);
      expect((connection!.transport as NativeBleTransport).requiresBond, isFalse);
    });
  });
}
