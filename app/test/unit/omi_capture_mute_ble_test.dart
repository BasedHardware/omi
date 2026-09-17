import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class _MuteTransport extends DeviceTransport {
  _MuteTransport({this.features = OmiFeatures.captureMute, this.muteValue = const [1]});

  final int features;
  List<int> muteValue;
  final List<(String, String, List<int>)> writes = [];

  @override
  String get deviceId => 'omi-mute';

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
    if (characteristicUuid == OmiDeviceConnection.featuresCharacteristicUuid) {
      return [
        features & 0xff,
        (features >> 8) & 0xff,
        (features >> 16) & 0xff,
        (features >> 24) & 0xff,
      ];
    }
    if (characteristicUuid == OmiDeviceConnection.settingsMuteCharacteristicUuid) {
      return muteValue;
    }
    return [];
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    writes.add((serviceUuid, characteristicUuid, List<int>.from(data)));
  }

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  Future<void> dispose() async {}
}

OmiDeviceConnection _connection(_MuteTransport transport) {
  return OmiDeviceConnection(
    BtDevice(id: transport.deviceId, name: 'Omi', type: DeviceType.omi, rssi: -40),
    transport,
  );
}

void main() {
  test('writes capture mute to the pendant settings characteristic', () async {
    final transport = _MuteTransport();
    final connection = _connection(transport);

    await connection.setCaptureMuted(true);

    expect(transport.writes, hasLength(1));
    expect(transport.writes.single.$1, OmiDeviceConnection.settingsServiceUuid);
    expect(transport.writes.single.$2, OmiDeviceConnection.settingsMuteCharacteristicUuid);
    expect(transport.writes.single.$3, [1]);
  });

  test('reads paused state from the pendant after reconnect', () async {
    final transport = _MuteTransport(muteValue: [1]);
    final connection = _connection(transport);

    expect(await connection.getCaptureMuted(), isTrue);
  });

  test('legacy firmware without the mute feature does not write and reports unknown', () async {
    final transport = _MuteTransport(features: OmiFeatures.micGain);
    final connection = _connection(transport);

    await connection.setCaptureMuted(true);
    expect(transport.writes, isEmpty);
    expect(await connection.getCaptureMuted(), isNull);
  });
}
