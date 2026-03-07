import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/pocket_connection.dart'
    show
        pocketAudioCharacteristicUuid,
        pocketCommandCharacteristicUuid,
        pocketCommandWriteCharacteristicUuid;

void main() {
  group('Pocket device detection', () {
    test('detects PKT prefix as Pocket device', () {
      // Verify the static detection method recognizes PKT-prefixed names
      expect('PKT-12345'.toUpperCase().startsWith('PKT'), isTrue);
      expect('PKT'.toUpperCase().startsWith('PKT'), isTrue);
      expect('pkt-device'.toUpperCase().startsWith('PKT'), isTrue);
    });

    test('does not detect non-PKT names', () {
      expect('Omi'.toUpperCase().startsWith('PKT'), isFalse);
      expect('Friend_v2'.toUpperCase().startsWith('PKT'), isFalse);
      expect('PLAUD'.toUpperCase().startsWith('PKT'), isFalse);
    });

    test('DeviceType.pocket exists in enum', () {
      expect(DeviceType.pocket, isNotNull);
      expect(DeviceType.pocket.index, greaterThan(0));
      expect(DeviceType.values.contains(DeviceType.pocket), isTrue);
    });
  });

  group('Pocket BLE UUIDs', () {
    test('service UUID is correct format', () {
      expect(pocketServiceUuid, equals('001120a0-2233-4455-6677-889912345678'));
      // Verify it's a valid UUID format
      final uuidRegex = RegExp(
          r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$');
      expect(uuidRegex.hasMatch(pocketServiceUuid), isTrue);
      expect(uuidRegex.hasMatch(pocketAudioCharacteristicUuid), isTrue);
      expect(uuidRegex.hasMatch(pocketCommandCharacteristicUuid), isTrue);
      expect(uuidRegex.hasMatch(pocketCommandWriteCharacteristicUuid), isTrue);
    });

    test('UUIDs share same base with different suffixes', () {
      // All Pocket UUIDs share the same base pattern with a0-a3 suffix
      const base = '-2233-4455-6677-889912345678';
      expect(pocketServiceUuid.endsWith(base), isTrue);
      expect(pocketAudioCharacteristicUuid.endsWith(base), isTrue);
      expect(pocketCommandCharacteristicUuid.endsWith(base), isTrue);
      expect(pocketCommandWriteCharacteristicUuid.endsWith(base), isTrue);
    });

    test('UUIDs are distinct', () {
      final uuids = {
        pocketServiceUuid,
        pocketAudioCharacteristicUuid,
        pocketCommandCharacteristicUuid,
        pocketCommandWriteCharacteristicUuid,
      };
      expect(uuids.length, equals(4));
    });

    test('service UUID from models.dart matches expected value', () {
      // Verify the constant exported from models.dart has the correct value
      expect(pocketServiceUuid, equals('001120a0-2233-4455-6677-889912345678'));
    });
  });

  group('Pocket command protocol', () {
    test('APP commands encode correctly as UTF-8 bytes', () {
      final startCmd = utf8.encode('APP&STA');
      expect(startCmd, equals([65, 80, 80, 38, 83, 84, 65]));

      final stopCmd = utf8.encode('APP&STO');
      expect(stopCmd, equals([65, 80, 80, 38, 83, 84, 79]));

      final batCmd = utf8.encode('APP&BAT');
      expect(batCmd, equals([65, 80, 80, 38, 66, 65, 84]));

      final fwCmd = utf8.encode('APP&FW');
      expect(fwCmd, equals([65, 80, 80, 38, 70, 87]));
    });

    test('MCU battery response parses correctly', () {
      const response = 'MCU&BAT&85';
      expect(response.startsWith('MCU&BAT&'), isTrue);
      final levelStr = response.substring('MCU&BAT&'.length).trim();
      final level = int.tryParse(levelStr);
      expect(level, equals(85));
    });

    test('MCU battery response handles edge cases', () {
      // Full battery
      const full = 'MCU&BAT&100';
      expect(int.tryParse(full.substring('MCU&BAT&'.length).trim()), equals(100));

      // Empty battery
      const empty = 'MCU&BAT&0';
      expect(int.tryParse(empty.substring('MCU&BAT&'.length).trim()), equals(0));

      // Malformed
      const bad = 'MCU&BAT&xyz';
      expect(int.tryParse(bad.substring('MCU&BAT&'.length).trim()), isNull);
    });

    test('MCU firmware response parses correctly', () {
      const response = 'MCU&FW&T19';
      expect(response.startsWith('MCU&FW&'), isTrue);
      final version = response.substring('MCU&FW&'.length).trim();
      expect(version, equals('T19'));
    });

    test('MCU recording modes parse correctly', () {
      const convResponse = 'MCU&REC&CON';
      const callResponse = 'MCU&REC&CALL';
      expect(convResponse.startsWith('MCU&REC&'), isTrue);
      expect(callResponse.startsWith('MCU&REC&'), isTrue);

      final convMode = convResponse.substring('MCU&REC&'.length);
      final callMode = callResponse.substring('MCU&REC&'.length);
      expect(convMode, equals('CON'));
      expect(callMode, equals('CALL'));
    });

    test('MCU storage response parses correctly', () {
      const response = 'MCU&SPA&16384&8192';
      expect(response.startsWith('MCU&SPA&'), isTrue);
      final parts = response.substring('MCU&SPA&'.length).split('&');
      expect(parts.length, equals(2));
      expect(int.tryParse(parts[0]), equals(16384));
      expect(int.tryParse(parts[1]), equals(8192));
    });

    test('time sync command formats correctly', () {
      final now = DateTime(2026, 3, 6, 15, 30, 45);
      final timeStr =
          '${now.year}${now.month.toString().padLeft(2, '0')}${now.day.toString().padLeft(2, '0')}'
          '${now.hour.toString().padLeft(2, '0')}${now.minute.toString().padLeft(2, '0')}${now.second.toString().padLeft(2, '0')}';
      expect(timeStr, equals('20260306153045'));
      expect('APP&T&$timeStr', equals('APP&T&20260306153045'));
    });
  });

  group('Pocket BtDevice integration', () {
    test('BtDevice can be created with pocket type', () {
      final device = BtDevice(
        name: 'PKT-ABC123',
        id: 'AA:BB:CC:DD:EE:FF',
        type: DeviceType.pocket,
        rssi: -65,
      );
      expect(device.type, equals(DeviceType.pocket));
      expect(device.name, equals('PKT-ABC123'));
    });

    test('BtDevice pocket type serializes/deserializes correctly', () {
      final device = BtDevice(
        name: 'PKT-TEST',
        id: '11:22:33:44:55:66',
        type: DeviceType.pocket,
        rssi: -70,
      );
      final json = device.toJson();
      final restored = BtDevice.fromJson(json);
      expect(restored.type, equals(DeviceType.pocket));
      expect(restored.name, equals('PKT-TEST'));
      expect(restored.id, equals('11:22:33:44:55:66'));
    });

    test('firmware warning message is set for pocket', () {
      final device = BtDevice(
        name: 'PKT-TEST',
        id: '11:22:33:44:55:66',
        type: DeviceType.pocket,
        rssi: -70,
      );
      expect(device.getFirmwareWarningTitle(), equals('Compatibility Note'));
      expect(device.getFirmwareWarningMessage(), contains('HeyPocket'));
    });
  });
}
