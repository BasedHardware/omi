import 'package:flutter/foundation.dart';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/services/devices/transports/native_ble_transport.dart';

class _MuteTransport extends DeviceTransport {
  _MuteTransport({this.features = OmiFeatures.captureMute, this.muteValue = const [1]});

  final int features;
  List<int> muteValue;
  Object? writeError;
  Object? featureReadError;
  bool acceptWrite = true;
  bool malformedFeatures = false;
  int featureReadFailures = 0;
  int featureReads = 0;
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
      featureReads++;
      if (featureReadFailures > 0) {
        featureReadFailures--;
        return [];
      }
      if (featureReadError != null) throw featureReadError!;
      if (malformedFeatures) return [];
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
    if (writeError != null) throw writeError!;
    writes.add((serviceUuid, characteristicUuid, List<int>.from(data)));
    if (acceptWrite) muteValue = List<int>.from(data);
  }

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  Future<void> dispose() async {}
}

class _HostApi extends BleHostApi {
  int reads = 0;
  final writes = <String>[];

  @override
  Future<Uint8List> readCharacteristic(String peripheralUuid, String serviceUuid, String characteristicUuid) async {
    reads++;
    return Uint8List(0);
  }

  @override
  Future<void> writeCharacteristic(
      String peripheralUuid, String serviceUuid, String characteristicUuid, Uint8List value) async {
    writes.add(characteristicUuid);
  }

  @override
  Future<void> unsubscribeCharacteristic(String peripheralUuid, String serviceUuid, String characteristicUuid) async {}
}

OmiDeviceConnection _connection(DeviceTransport transport) {
  return OmiDeviceConnection(
    BtDevice(id: transport.deviceId, name: 'Omi', type: DeviceType.omi, rssi: -40),
    transport,
  );
}

void main() {
  setUp(() => OmiDeviceConnection.captureMuteRetryDelay = Duration.zero);
  test('capture mute owns 19B10015 / feature bit 10, not the device-name slot', () {
    // #13704 allocated 19B10014 / bit 9 for device name first. Mute must not
    // collide (BasedHardware/omi#14293 vs #13704).
    expect(
      OmiDeviceConnection.settingsMuteCharacteristicUuid,
      '19b10015-e8f2-537e-4f6c-d104768a1214',
    );
    expect(OmiDeviceConnection.settingsMuteCharacteristicUuid, isNot('19b10014-e8f2-537e-4f6c-d104768a1214'));
    expect(OmiFeatures.captureMute, 1 << 10);
    expect(OmiFeatures.captureMute, isNot(1 << 9));
  });

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

  test('a refused mute write reaches the caller', () async {
    final transport = _MuteTransport()..writeError = StateError('ATT persistence failure');
    await expectLater(_connection(transport).setCaptureMuted(true), throwsStateError);
  });

  test('unmute is acknowledged only when the device confirms the new state', () async {
    final transport = _MuteTransport()..acceptWrite = false;
    await expectLater(_connection(transport).setCaptureMuted(false), throwsStateError);
    transport.acceptWrite = true;
    await _connection(transport).setCaptureMuted(false);
    expect(transport.muteValue, [0]);
  });

  test('failed or malformed feature reads are not mistaken for legacy firmware', () async {
    final transport = _MuteTransport()..featureReadError = StateError('disconnected');
    await expectLater(_connection(transport).setCaptureMuted(true), throwsStateError);
    transport.featureReadError = null;
    transport.malformedFeatures = true;
    await expectLater(_connection(transport).setCaptureMuted(true), throwsStateError);
    expect(transport.writes, isEmpty);
  });

  test('legacy firmware without the mute feature does not write and reports unknown', () async {
    final transport = _MuteTransport(features: OmiFeatures.micGain);
    final connection = _connection(transport);

    await connection.setCaptureMuted(true);
    expect(transport.writes, isEmpty);
    expect(await connection.getCaptureMuted(), isNull);
  });

  test('a features read that fails once is retried before the pause is written', () async {
    final transport = _MuteTransport()..featureReadFailures = 1;

    await _connection(transport).setCaptureMuted(true);

    expect(transport.featureReads, 2);
    expect(transport.writes.single.$3, [1]);
  });

  test('a features read that fails twice still reaches the caller', () async {
    final transport = _MuteTransport()..featureReadFailures = 2;

    await expectLater(_connection(transport).setCaptureMuted(true), throwsStateError);
    expect(transport.featureReads, 2);
    expect(transport.writes, isEmpty);
  });

  group('native transport', () {
    const uuid = 'AA:BB:CC:DD:EE:01';
    late _HostApi host;
    late NativeBleTransport transport;

    setUp(() {
      host = _HostApi();
      transport = NativeBleTransport(uuid, hostApi: host);
    });
    tearDown(() => transport.dispose());

    test('a discovered pendant without the features characteristic is legacy: no write, no error', () async {
      BleBridge.instance.onDeviceReady(uuid, [
        BleService(
          uuid: OmiDeviceConnection.settingsServiceUuid,
          characteristicUuids: [OmiDeviceConnection.settingsMuteCharacteristicUuid],
        ),
      ]);

      await _connection(transport).setCaptureMuted(true);

      expect(host.reads, 0);
      expect(host.writes, isEmpty);
    });

    test('before discovery a missing characteristic is not mistaken for legacy firmware', () async {
      await expectLater(_connection(transport).setCaptureMuted(true), throwsStateError);
      expect(host.writes, isEmpty);
    });
  });
}
