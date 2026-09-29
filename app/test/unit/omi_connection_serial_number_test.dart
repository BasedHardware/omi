import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

/// Serves fixed DIS reads. A characteristic absent from [reads] behaves like
/// firmware that does not expose it: the native transport returns an empty read.
class _DisTransport extends DeviceTransport {
  _DisTransport(this.reads, {this.throwOnSerial = false});

  final Map<String, List<int>> reads;
  final bool throwOnSerial;

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
    if (throwOnSerial && characteristicUuid == serialNumberCharacteristicUuid) {
      throw StateError('GATT read failed');
    }
    return reads[characteristicUuid] ?? [];
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {}

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  Future<void> dispose() async {}
}

Map<String, List<int>> _cv1Reads({String? serial}) => {
      modelNumberCharacteristicUuid: 'Omi CV 1'.codeUnits,
      firmwareRevisionCharacteristicUuid: '3.0.21'.codeUnits,
      hardwareRevisionCharacteristicUuid: '5.0'.codeUnits,
      manufacturerNameCharacteristicUuid: 'Based Hardware'.codeUnits,
      if (serial != null) serialNumberCharacteristicUuid: serial.codeUnits,
    };

BtDevice _device() => BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

Future<BtDevice> _resolve(_DisTransport transport) =>
    _device().getDeviceInfo(OmiDeviceConnection(_device(), transport));

void main() {
  group('CV1 DIS serial number', () {
    test('firmware without 0x2A25 keeps device info and leaves serial unset', () async {
      final device = await _resolve(_DisTransport(_cv1Reads()));

      expect(device.modelNumber, 'Omi CV 1');
      expect(device.firmwareRevision, '3.0.21');
      expect(device.hardwareRevision, '5.0');
      expect(device.manufacturerName, 'Based Hardware');
      expect(device.serialNumber, isNull);
    });

    test('firmware exposing the unit ID populates serialNumber', () async {
      final device = await _resolve(_DisTransport(_cv1Reads(serial: '1A2B3C4D5E6F7081')));

      expect(device.serialNumber, '1A2B3C4D5E6F7081');
      expect(device.firmwareRevision, '3.0.21');
    });

    test('firmware fallback placeholder is not treated as a serial', () async {
      final device = await _resolve(_DisTransport(_cv1Reads(serial: 'unknown')));

      expect(device.serialNumber, isNull);
    });

    test('a failing serial read does not drop the other DIS fields', () async {
      final device = await _resolve(_DisTransport(_cv1Reads(serial: '1A2B3C4D5E6F7081'), throwOnSerial: true));

      expect(device.serialNumber, isNull);
      expect(device.modelNumber, 'Omi CV 1');
      expect(device.firmwareRevision, '3.0.21');
    });
  });

  group('parseSerialNumber', () {
    test('rejects empty, placeholder and single-character-run values', () {
      for (final value in ['', '   ', 'unknown', 'UNKNOWN', 'None', 'n/a', '0000000000000000', 'FFFFFFFFFFFFFFFF']) {
        expect(OmiDeviceConnection.parseSerialNumber(value.codeUnits), isNull, reason: value);
      }
    });

    test('trims whitespace and NUL padding', () {
      expect(OmiDeviceConnection.parseSerialNumber([...' 1A2B3C4D5E6F7081'.codeUnits, 0, 0]), '1A2B3C4D5E6F7081');
    });
  });
}
