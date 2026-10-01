import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class _ProbeTransport extends DeviceTransport {
  _ProbeTransport({required this.hasTapsChar, this.features = 0, this.connected = true});

  final bool hasTapsChar;
  final int features;
  final bool connected;

  @override
  String get deviceId => 'probe';

  @override
  bool hasCharacteristic(String serviceUuid, String characteristicUuid) {
    return hasTapsChar &&
        serviceUuid.toLowerCase() == buttonServiceUuid.toLowerCase() &&
        characteristicUuid.toLowerCase() == buttonTapsCharacteristicUuid.toLowerCase();
  }

  @override
  Future<bool> isConnected() async => connected;

  @override
  Future<void> connect() async {}

  @override
  Future<void> disconnect() async {}

  @override
  Future<bool> ping() async => connected;

  @override
  Future<void> dispose() async {}

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) => const Stream.empty();

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    if (serviceUuid == OmiDeviceConnection.featuresServiceUuid &&
        characteristicUuid == OmiDeviceConnection.featuresCharacteristicUuid) {
      final data = ByteData(4)..setUint32(0, features, Endian.little);
      return data.buffer.asUint8List();
    }
    return [];
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {}

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();
}

OmiDeviceConnection _connection(_ProbeTransport transport) => OmiDeviceConnection(
      BtDevice(id: transport.deviceId, name: 'Omi', type: DeviceType.omi, rssi: -40),
      transport,
    );

void main() {
  test('supportsButtonTaps is true when feature bit 9 is set', () async {
    final connection = _connection(_ProbeTransport(hasTapsChar: false, features: OmiFeatures.buttonTaps));
    expect(await connection.supportsButtonTaps(), isTrue);
  });

  test('supportsButtonTaps probes GATT when features are zero (DevKit)', () async {
    final withChar = _connection(_ProbeTransport(hasTapsChar: true));
    final withoutChar = _connection(_ProbeTransport(hasTapsChar: false));
    expect(await withChar.supportsButtonTaps(), isTrue);
    expect(await withoutChar.supportsButtonTaps(), isFalse);
  });

  test('getBleButtonTapsListener returns null when characteristic is absent', () async {
    final connection = _connection(_ProbeTransport(hasTapsChar: false));
    final sub = await connection.getBleButtonTapsListener(onTapsReceived: (_) {});
    expect(sub, isNull);
  });

  test('getBleButtonTapsListener subscribes when characteristic is present', () async {
    final connection = _connection(_ProbeTransport(hasTapsChar: true));
    final sub = await connection.getBleButtonTapsListener(onTapsReceived: (_) {});
    expect(sub, isNotNull);
    await sub!.cancel();
  });

  test('supportsButtonTaps is false when disconnected', () async {
    final connection = _connection(_ProbeTransport(hasTapsChar: true, connected: false));
    expect(await connection.supportsButtonTaps(), isFalse);
  });
}
