import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class FakeDeviceTransport extends DeviceTransport {
  final writes = <(String, List<int>)>[];
  final reads = <String, List<int>>{};

  @override
  Future<void> connect() async {}

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  String get deviceId => 'test';

  @override
  Future<void> disconnect() async {}

  @override
  Future<void> dispose() async {}

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) => const Stream.empty();

  @override
  Future<bool> isConnected() async => true;

  @override
  Future<bool> ping() async => true;

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async =>
      reads[characteristicUuid] ?? [];

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    writes.add((characteristicUuid, data));
  }
}

void main() {
  test('writes sleep and device name controls', () async {
    final transport = FakeDeviceTransport();
    final connection = OmiDeviceConnection(BtDevice(id: 'test', name: 'Omi', type: DeviceType.omi, rssi: 0), transport);

    expect(await connection.sleepDevice(), isTrue);
    expect(await connection.setDeviceName('Desk Omi'), isTrue);
    expect(transport.writes.map((write) => write.$1), [
      OmiDeviceConnection.settingsSleepCommandCharacteristicUuid,
      OmiDeviceConnection.settingsDeviceNameCharacteristicUuid,
    ]);
    expect(transport.writes.map((write) => write.$2), [
      [1],
      'Desk Omi'.codeUnits,
    ]);
  });

  test('rejects invalid names and reads UTF-8 names', () async {
    final transport = FakeDeviceTransport();
    final connection = OmiDeviceConnection(BtDevice(id: 'test', name: 'Omi', type: DeviceType.omi, rssi: 0), transport);
    transport.reads[OmiDeviceConnection.settingsDeviceNameCharacteristicUuid] = [79, 109, 105];

    expect(await connection.setDeviceName(' '), isFalse);
    expect(await connection.setDeviceName(List.filled(26, 'x').join()), isFalse);
    expect(await connection.readDeviceName(), 'Omi');
    expect(transport.writes, isEmpty);
  });
}
