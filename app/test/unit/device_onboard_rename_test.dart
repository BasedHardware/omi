import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class _MockTransport implements DeviceTransport {
  _MockTransport(this.deviceId);

  @override
  final String deviceId;

  final Map<String, List<int>> characteristics = {};
  final List<Map<String, dynamic>> writeCalls = [];

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    writeCalls.add({
      'serviceUuid': serviceUuid,
      'characteristicUuid': characteristicUuid,
      'data': data,
    });
    characteristics['$serviceUuid/$characteristicUuid'] = data;
  }

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    return characteristics['$serviceUuid/$characteristicUuid'] ?? <int>[];
  }

  @override
  Future<void> dispose() async {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const testDeviceId = '11:22:33:44:55:66';

  group('OmiDeviceConnection Device Onboard Rename', () {
    late _MockTransport transport;
    late BtDevice device;
    late OmiDeviceConnection connection;

    setUp(() {
      transport = _MockTransport(testDeviceId);
      device = BtDevice(
        id: testDeviceId,
        name: 'Omi DevKit',
        type: DeviceType.omi,
        rssi: -60,
        locator: DeviceLocator.bluetooth(deviceId: testDeviceId),
      );
      connection = OmiDeviceConnection(device, transport);
    });

    test('performSetDeviceName encodes string to UTF-8 and writes to characteristic', () async {
      const newName = "Alice's Omi";
      await connection.performSetDeviceName(newName);

      expect(transport.writeCalls.length, 1);
      final call = transport.writeCalls.first;
      expect(call['serviceUuid'], OmiDeviceConnection.settingsServiceUuid);
      expect(call['characteristicUuid'], OmiDeviceConnection.settingsDeviceNameCharacteristicUuid);
      expect(call['data'], utf8.encode(newName));
    });

    test('performSetDeviceName clamps string exceeding 31 bytes', () async {
      const veryLongName = "1234567890123456789012345678901234567890";
      await connection.performSetDeviceName(veryLongName);

      expect(transport.writeCalls.length, 1);
      final call = transport.writeCalls.first;
      final writtenBytes = call['data'] as List<int>;
      expect(writtenBytes.length, 31);
      expect(utf8.decode(writtenBytes), veryLongName.substring(0, 31));
    });

    test('performGetDeviceName decodes string from characteristic', () async {
      const savedName = "Bob's Omi";
      transport.characteristics[
              '${OmiDeviceConnection.settingsServiceUuid}/${OmiDeviceConnection.settingsDeviceNameCharacteristicUuid}'] =
          utf8.encode(savedName);

      final result = await connection.performGetDeviceName();
      expect(result, savedName);
    });

    test('performGetDeviceName returns null when characteristic is empty', () async {
      transport.characteristics[
          '${OmiDeviceConnection.settingsServiceUuid}/${OmiDeviceConnection.settingsDeviceNameCharacteristicUuid}'] = [];

      final result = await connection.performGetDeviceName();
      expect(result, isNull);
    });

    test('performGetDeviceName returns null when characteristic is only whitespace', () async {
      transport.characteristics[
              '${OmiDeviceConnection.settingsServiceUuid}/${OmiDeviceConnection.settingsDeviceNameCharacteristicUuid}'] =
          utf8.encode('   ');

      final result = await connection.performGetDeviceName();
      expect(result, isNull);
    });
  });

  group('BtDevice Onboard Name Sync', () {
    test('getDeviceInfo updates BtDevice.name when onboard name is present', () async {
      final transport = _MockTransport(testDeviceId);
      transport.characteristics[
              '${OmiDeviceConnection.settingsServiceUuid}/${OmiDeviceConnection.settingsDeviceNameCharacteristicUuid}'] =
          utf8.encode("Charlie's Omi");

      final baseDevice = BtDevice(
        id: testDeviceId,
        name: 'Omi DevKit',
        type: DeviceType.omi,
        rssi: -55,
        locator: DeviceLocator.bluetooth(deviceId: testDeviceId),
      );
      final connection = OmiDeviceConnection(baseDevice, transport);

      final updatedDevice = await baseDevice.getDeviceInfo(connection);
      expect(updatedDevice.name, "Charlie's Omi");
    });

    test('getDeviceInfo keeps default BtDevice.name when onboard name is absent', () async {
      final transport = _MockTransport(testDeviceId);
      final baseDevice = BtDevice(
        id: testDeviceId,
        name: 'Omi DevKit',
        type: DeviceType.omi,
        rssi: -55,
        locator: DeviceLocator.bluetooth(deviceId: testDeviceId),
      );
      final connection = OmiDeviceConnection(baseDevice, transport);

      final updatedDevice = await baseDevice.getDeviceInfo(connection);
      expect(updatedDevice.name, 'Omi DevKit');
    });

    test('getDeviceInfo keeps original name when getDeviceName throws', () async {
      final transport = _MockTransport(testDeviceId);
      final baseDevice = BtDevice(
        id: testDeviceId,
        name: 'Omi DevKit',
        type: DeviceType.omi,
        rssi: -55,
        locator: DeviceLocator.bluetooth(deviceId: testDeviceId),
      );
      final connection = OmiDeviceConnection(baseDevice, transport);

      final updatedDevice = await baseDevice.getDeviceInfo(connection);
      expect(updatedDevice.name, 'Omi DevKit');
    });
  });
}
