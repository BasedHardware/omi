import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/utils/utf8_byte_limit_formatter.dart';

class _MockRenameTransport extends DeviceTransport {
  _MockRenameTransport({this.initialNameBytes = const []});

  List<int> initialNameBytes;
  List<int>? writtenBytes;
  bool throwOnRead = false;
  bool throwOnWrite = false;
  // Simulates a write the GATT stack acked but the firmware did not persist.
  bool dropWrites = false;

  @override
  String get deviceId => 'omi-rename-1';

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
    if (throwOnRead) {
      throw StateError('GATT read failure');
    }
    if (characteristicUuid == OmiDeviceConnection.settingsDeviceNameCharacteristicUuid) {
      return writtenBytes ?? initialNameBytes;
    }
    if (characteristicUuid == modelNumberCharacteristicUuid) {
      return 'Omi CV 1'.codeUnits;
    }
    if (characteristicUuid == firmwareRevisionCharacteristicUuid) {
      return '3.0.21'.codeUnits;
    }
    return [];
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    if (throwOnWrite) {
      throw StateError('GATT write failure');
    }
    if (characteristicUuid == OmiDeviceConnection.settingsDeviceNameCharacteristicUuid && !dropWrites) {
      writtenBytes = List<int>.from(data);
    }
  }

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  Future<void> dispose() async {}
}

class _DummyBaseConnection extends DeviceConnection {
  _DummyBaseConnection()
      : super(
          BtDevice(id: 'dummy', name: 'Dummy', type: DeviceType.omi, rssi: -50),
          _MockRenameTransport(),
        );

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  group('OmiDeviceConnection.truncateUtf8ToBytes', () {
    test('ASCII string within 25 bytes is preserved exactly', () {
      const input = 'Studio Omi';
      final bytes = OmiDeviceConnection.truncateUtf8ToBytes(input, 25);
      expect(utf8.decode(bytes), 'Studio Omi');
      expect(bytes.length, 10);
    });

    test('ASCII string exceeding 25 bytes is clamped to 25 bytes', () {
      const input = 'This is a very long device name exceeding 25';
      final bytes = OmiDeviceConnection.truncateUtf8ToBytes(input, 25);
      expect(bytes.length, 25);
      expect(utf8.decode(bytes), 'This is a very long devic');
    });

    test('multi-byte UTF-8 sequence is not torn in the middle', () {
      // Each character '一' is 3 bytes in UTF-8.
      // 9 characters = 27 bytes.
      // Clamping to 25 bytes must cleanly yield 8 characters (24 bytes), NOT a broken 25th byte.
      const input = '一二三四五六七八九';
      final bytes = OmiDeviceConnection.truncateUtf8ToBytes(input, 25);
      expect(bytes.length, 24);
      expect(utf8.decode(bytes), '一二三四五六七八');
    });

    test('empty string yields empty bytes', () {
      expect(OmiDeviceConnection.truncateUtf8ToBytes('', 25), isEmpty);
    });
  });

  group('OmiDeviceConnection GATT rename operations', () {
    test('performSetDeviceName writes clamped bytes and performGetDeviceName reads it back', () async {
      final transport = _MockRenameTransport();
      final device = BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
      final conn = OmiDeviceConnection(device, transport);

      final success = await conn.performSetDeviceName('Office Pendant');
      expect(success, isTrue);
      expect(utf8.decode(transport.writtenBytes!), 'Office Pendant');

      final readBack = await conn.performGetDeviceName();
      expect(readBack, 'Office Pendant');
    });

    test('performSetDeviceName handles GATT write error gracefully', () async {
      final transport = _MockRenameTransport()..throwOnWrite = true;
      final device = BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
      final conn = OmiDeviceConnection(device, transport);

      final success = await conn.performSetDeviceName('Office Pendant');
      expect(success, isFalse);
    });

    test('performGetDeviceName handles GATT read error gracefully', () async {
      final transport = _MockRenameTransport()..throwOnRead = true;
      final device = BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
      final conn = OmiDeviceConnection(device, transport);

      final readBack = await conn.performGetDeviceName();
      expect(readBack, isNull);
    });

    test('getDeviceInfo includes custom onboard deviceName and updates BtDevice.name', () async {
      final transport = _MockRenameTransport(
        initialNameBytes: utf8.encode('Custom Omi Hardware'),
      );
      final device = BtDevice(id: 'omi-1', name: 'Default Omi', type: DeviceType.omi, rssi: -40);
      final conn = OmiDeviceConnection(device, transport);

      final info = await conn.getDeviceInfo();
      expect(info['deviceName'], 'Custom Omi Hardware');

      final updated = await device.getDeviceInfo(conn);
      expect(updated.name, 'Custom Omi Hardware');
    });
  });

  group('DeviceConnection polymorphic defaults', () {
    test('base connection setDeviceName and getDeviceName have safe defaults', () async {
      final conn = _DummyBaseConnection();
      expect(await conn.setDeviceName('New Name'), isFalse);
      expect(await conn.getDeviceName(), isNull);
    });
  });

  group('DeviceProvider.persistNameOnboard read-back', () {
    OmiDeviceConnection conn(_MockRenameTransport t) =>
        OmiDeviceConnection(BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40), t);

    test('write + matching read-back reports savedOnDevice', () async {
      final t = _MockRenameTransport();
      final c = conn(t);
      expect(await DeviceProvider.persistNameOnboard(c, 'Office Pendant'), DeviceRenameResult.savedOnDevice);
    });

    test('GATT write error reports deviceWriteFailed (not silent success)', () async {
      final t = _MockRenameTransport()..throwOnWrite = true;
      expect(await DeviceProvider.persistNameOnboard(conn(t), 'Office Pendant'), DeviceRenameResult.deviceWriteFailed);
    });

    test('acked write that did not persist is caught by read-back', () async {
      final t = _MockRenameTransport(initialNameBytes: utf8.encode('Old Name'))..dropWrites = true;
      expect(await DeviceProvider.persistNameOnboard(conn(t), 'Office Pendant'), DeviceRenameResult.deviceWriteFailed);
    });

    test('read-back failure reports deviceWriteFailed', () async {
      final t = _MockRenameTransport()..throwOnRead = true;
      expect(await DeviceProvider.persistNameOnboard(conn(t), 'Office Pendant'), DeviceRenameResult.deviceWriteFailed);
    });

    test('Omi connections advertise onboard-name support; base connections do not', () {
      expect(conn(_MockRenameTransport()).supportsOnboardDeviceName, isTrue);
      expect(_DummyBaseConnection().supportsOnboardDeviceName, isFalse);
    });
  });

  group('25-byte device-name budget', () {
    test('isValidDeviceName counts UTF-8 bytes, not characters', () {
      expect(SharedPreferencesUtil.maxDeviceNameBytes, OmiDeviceConnection.maxDeviceNameBytes);
      expect(SharedPreferencesUtil.isValidDeviceName('A' * 25), isTrue);
      expect(SharedPreferencesUtil.isValidDeviceName('A' * 26), isFalse);
      // 8 x 3-byte chars = 24 bytes OK; 9 = 27 bytes rejected.
      expect(SharedPreferencesUtil.isValidDeviceName('一二三四五六七八'), isTrue);
      expect(SharedPreferencesUtil.isValidDeviceName('一二三四五六七八九'), isFalse);
      expect(SharedPreferencesUtil.isValidDeviceName('   '), isFalse);
    });

    test('Utf8ByteLimitFormatter rejects input that would exceed the byte budget', () {
      final f = Utf8ByteLimitFormatter(25);
      final old = TextEditingValue(text: 'A' * 24);
      expect(f.formatEditUpdate(old, TextEditingValue(text: 'A' * 25)).text, 'A' * 25);
      expect(f.formatEditUpdate(old, TextEditingValue(text: '${'A' * 24}é')).text, 'A' * 24);
      expect(f.formatEditUpdate(old, TextEditingValue(text: '${'A' * 23}é')).text, '${'A' * 23}é');
    });
  });
}
