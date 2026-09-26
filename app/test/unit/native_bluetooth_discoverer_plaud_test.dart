import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/devices/discovery/native_bluetooth_discoverer.dart';
import 'package:omi/services/devices/models.dart';

void main() {
  group('NativeBluetoothDiscoverer PLAUD and NotePin S discovery (#14376)', () {
    test('identifies classic PLAUD NOTE device by prefix', () {
      final peripheral = BlePeripheral(
        uuid: '0000-1111-2222',
        name: 'PLAUD NOTE',
        rssi: -55,
        serviceUuids: [],
      );

      expect(NativeBluetoothDiscoverer.isPlaud(peripheral), isTrue);
      expect(NativeBluetoothDiscoverer.isSupportedPeripheral(peripheral), isTrue);

      final device = NativeBluetoothDiscoverer.peripheralToDevice(peripheral);
      expect(device.type, DeviceType.plaud);
      expect(device.name, 'PLAUD NOTE');
      expect(device.id, '0000-1111-2222');
    });

    test('identifies PLAUD NotePin S device (#14376)', () {
      final peripheral = BlePeripheral(
        uuid: '0000-2222-3333',
        name: 'NotePin S',
        rssi: -62,
        serviceUuids: [],
      );

      expect(NativeBluetoothDiscoverer.isPlaud(peripheral), isTrue);
      expect(NativeBluetoothDiscoverer.isSupportedPeripheral(peripheral), isTrue);

      final device = NativeBluetoothDiscoverer.peripheralToDevice(peripheral);
      expect(device.type, DeviceType.plaud);
      expect(device.name, 'NotePin S');
    });

    test('identifies uppercase NOTEPIN with suffix identifier', () {
      final peripheral = BlePeripheral(
        uuid: '0000-3333-4444',
        name: 'NOTEPIN-B892',
        rssi: -48,
        serviceUuids: [],
      );

      expect(NativeBluetoothDiscoverer.isPlaud(peripheral), isTrue);
      expect(NativeBluetoothDiscoverer.isSupportedPeripheral(peripheral), isTrue);

      final device = NativeBluetoothDiscoverer.peripheralToDevice(peripheral);
      expect(device.type, DeviceType.plaud);
      expect(device.name, 'NOTEPIN-B892');
    });

    test('identifies PLAUD device via plaudServiceUuid even if name is customized', () {
      final peripheral = BlePeripheral(
        uuid: '0000-4444-5555',
        name: 'My Audio Recorder',
        rssi: -70,
        serviceUuids: [plaudServiceUuid],
      );

      expect(NativeBluetoothDiscoverer.isPlaud(peripheral), isTrue);
      expect(NativeBluetoothDiscoverer.isSupportedPeripheral(peripheral), isTrue);

      final device = NativeBluetoothDiscoverer.peripheralToDevice(peripheral);
      expect(device.type, DeviceType.plaud);
    });

    test('identifies PLAUD device with case-insensitive service UUID', () {
      final peripheral = BlePeripheral(
        uuid: '0000-5555-6666',
        name: 'Custom Wearable',
        rssi: -68,
        serviceUuids: [plaudServiceUuid.toUpperCase()],
      );

      expect(NativeBluetoothDiscoverer.isPlaud(peripheral), isTrue);
      expect(NativeBluetoothDiscoverer.isSupportedPeripheral(peripheral), isTrue);

      final device = NativeBluetoothDiscoverer.peripheralToDevice(peripheral);
      expect(device.type, DeviceType.plaud);
    });

    test('does not misidentify unrelated peripherals as PLAUD', () {
      final headphone = BlePeripheral(
        uuid: '0000-9999-0000',
        name: 'AirPods Pro',
        rssi: -40,
        serviceUuids: ['0000180a-0000-1000-8000-00805f9b34fb'],
      );

      expect(NativeBluetoothDiscoverer.isPlaud(headphone), isFalse);
      expect(NativeBluetoothDiscoverer.isSupportedPeripheral(headphone), isFalse);
    });

    test('does not conflict with other supported peripherals', () {
      final beeDevice = BlePeripheral(
        uuid: '0000-8888-1111',
        name: 'Bee Device',
        rssi: -50,
        serviceUuids: [],
      );

      expect(NativeBluetoothDiscoverer.isPlaud(beeDevice), isFalse);
      expect(NativeBluetoothDiscoverer.isSupportedPeripheral(beeDevice), isTrue);
      expect(NativeBluetoothDiscoverer.peripheralToDevice(beeDevice).type, DeviceType.bee);
    });
  });
}
