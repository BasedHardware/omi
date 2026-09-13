/// Renaming an Omi writes the settings device-name characteristic (19B10014)
/// and only reports success once the pendant reads the same name back, so a
/// rejected or unpersisted write never becomes the app's idea of the name.
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class _FakeOmiTransport extends DeviceTransport {
  _FakeOmiTransport({this.supportsDeviceName = true});

  /// Whether the (fake) firmware exposes the device-name characteristic.
  final bool supportsDeviceName;

  /// Name currently "stored" on the device.
  String storedName = 'Omi';

  /// When set, the next write to the name characteristic throws (ATT error).
  bool rejectNextNameWrite = false;

  /// When set, reads return this instead of [storedName] (simulates a device
  /// that acknowledged the write but did not apply it).
  String? readbackOverride;

  final List<(String, String, List<int>)> writes = [];

  static const _settings = OmiDeviceConnection.settingsServiceUuid;
  static const _name = OmiDeviceConnection.settingsDeviceNameCharacteristicUuid;

  @override
  String get deviceId => 'omi-1';

  @override
  Future<void> connect() async {}

  @override
  Future<void> disconnect() async {}

  @override
  Future<bool> isConnected() async => true;

  @override
  Future<bool> ping() async => true;

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) => const Stream.empty();

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    if (serviceUuid == _settings && characteristicUuid == _name) {
      if (!supportsDeviceName) throw StateError('characteristic not found');
      return utf8.encode(readbackOverride ?? storedName);
    }
    // Device Information / other characteristics: nothing to report.
    throw StateError('unsupported characteristic $characteristicUuid');
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    writes.add((serviceUuid, characteristicUuid, List<int>.from(data)));
    if (serviceUuid == _settings && characteristicUuid == _name) {
      if (!supportsDeviceName) throw StateError('characteristic not found');
      if (rejectNextNameWrite) {
        rejectNextNameWrite = false;
        throw StateError('ATT error 0x13 value not allowed');
      }
      storedName = utf8.decode(data);
    }
  }

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  Future<void> dispose() async {}
}

OmiDeviceConnection _connection(_FakeOmiTransport transport, {String name = 'Omi'}) =>
    OmiDeviceConnection(BtDevice(id: transport.deviceId, name: name, type: DeviceType.omi, rssi: -40), transport);

void main() {
  group('performSetDeviceName', () {
    test('writes UTF-8 to 19B10014, confirms by readback and updates the local record', () async {
      final transport = _FakeOmiTransport();
      final connection = _connection(transport);

      final ok = await connection.performSetDeviceName('Léo 🎧');

      expect(ok, isTrue);
      expect(transport.writes, hasLength(1));
      expect(transport.writes.single.$1, OmiDeviceConnection.settingsServiceUuid);
      expect(transport.writes.single.$2, OmiDeviceConnection.settingsDeviceNameCharacteristicUuid);
      expect(transport.writes.single.$3, utf8.encode('Léo 🎧'));
      expect(transport.storedName, 'Léo 🎧');
      expect(connection.device.name, 'Léo 🎧');
    });

    test('reports failure and keeps the old name when the device rejects the write', () async {
      final transport = _FakeOmiTransport()..rejectNextNameWrite = true;
      final connection = _connection(transport);

      expect(await connection.performSetDeviceName('New Name'), isFalse);
      expect(transport.storedName, 'Omi');
      expect(connection.device.name, 'Omi');
    });

    test('reports failure when the readback does not match what was written', () async {
      final transport = _FakeOmiTransport()..readbackOverride = 'Omi';
      final connection = _connection(transport);

      expect(await connection.performSetDeviceName('New Name'), isFalse);
      expect(connection.device.name, 'Omi');
    });

    test('never sends a name the firmware would reject', () async {
      final transport = _FakeOmiTransport();
      final connection = _connection(transport);

      expect(await connection.performSetDeviceName(''), isFalse);
      expect(await connection.performSetDeviceName('x' * 21), isFalse);
      expect(transport.writes, isEmpty);
    });
  });

  group('performGetDeviceName', () {
    test('returns the stored name', () async {
      final transport = _FakeOmiTransport()..storedName = 'Kitchen Omi';
      expect(await _connection(transport).performGetDeviceName(), 'Kitchen Omi');
    });

    test('returns null on firmware without the characteristic', () async {
      final transport = _FakeOmiTransport(supportsDeviceName: false);
      expect(await _connection(transport).performGetDeviceName(), isNull);
    });
  });

  group('getDeviceInfo', () {
    test('surfaces the on-device name so a new phone adopts it on connect', () async {
      final transport = _FakeOmiTransport()..storedName = 'Kitchen Omi';
      final info = await _connection(transport).getDeviceInfo();
      expect(info['deviceName'], 'Kitchen Omi');
    });

    test('omits deviceName on firmware without the characteristic', () async {
      final transport = _FakeOmiTransport(supportsDeviceName: false);
      final info = await _connection(transport).getDeviceInfo();
      expect(info.containsKey('deviceName'), isFalse);
    });

    test('BtDevice takes the on-device name over the locally cached one', () async {
      final transport = _FakeOmiTransport()..storedName = 'Kitchen Omi';
      final connection = _connection(transport, name: 'Omi');

      final updated = await connection.device.getDeviceInfo(connection);

      expect(updated.name, 'Kitchen Omi');
      expect(updated.id, 'omi-1');
    });

    test('BtDevice keeps the cached name on firmware without the characteristic', () async {
      final transport = _FakeOmiTransport(supportsDeviceName: false);
      final connection = _connection(transport, name: 'Omi');

      final updated = await connection.device.getDeviceInfo(connection);

      expect(updated.name, 'Omi');
    });
  });
}
