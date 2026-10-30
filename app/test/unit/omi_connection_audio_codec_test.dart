import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

/// Test transport simulating BLE GATT characteristic reads with configurable failure count.
class _CodecTestTransport extends DeviceTransport {
  _CodecTestTransport({this.failCount = 0, this.returnValue});

  int failCount;
  final List<int>? returnValue;
  int readAttempts = 0;

  @override
  String get deviceId => 'omi-test-codec';

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
    if (characteristicUuid == audioCodecCharacteristicUuid) {
      readAttempts++;
      if (readAttempts <= failCount) {
        throw StateError('GATT transient read error on attempt ');
      }
      return returnValue ?? [];
    }
    return [];
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {}

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  Future<void> dispose() async {}
}

BtDevice _testDevice() => BtDevice(id: 'omi-test-codec', name: 'Omi Test', type: DeviceType.omi, rssi: -40);

void main() {
  group('OmiDeviceConnection.performGetAudioCodec', () {
    test('retries transient failures and returns opus when subsequent attempt succeeds', () async {
      final transport = _CodecTestTransport(failCount: 2, returnValue: [20]);
      final connection = OmiDeviceConnection(_testDevice(), transport);

      final codec = await connection.performGetAudioCodec();
      expect(codec, BleAudioCodec.opus);
      expect(transport.readAttempts, 3);
    });

    test('returns pcm8 when characteristic explicitly yields 1', () async {
      final transport = _CodecTestTransport(returnValue: [1]);
      final connection = OmiDeviceConnection(_testDevice(), transport);

      final codec = await connection.performGetAudioCodec();
      expect(codec, BleAudioCodec.pcm8);
      expect(transport.readAttempts, 1);
    });

    test('returns opusFS320 when characteristic explicitly yields 21', () async {
      final transport = _CodecTestTransport(returnValue: [21]);
      final connection = OmiDeviceConnection(_testDevice(), transport);

      final codec = await connection.performGetAudioCodec();
      expect(codec, BleAudioCodec.opusFS320);
      expect(transport.readAttempts, 1);
    });

    test('exhausts retries and throws StateError on persistent GATT failure without defaulting to pcm8', () async {
      final transport = _CodecTestTransport(failCount: 99);
      final connection = OmiDeviceConnection(_testDevice(), transport);

      expect(() => connection.performGetAudioCodec(), throwsA(isA<StateError>()));
    });

    test('exhausts retries and throws StateError on persistent empty reads without defaulting to pcm8', () async {
      final transport = _CodecTestTransport(returnValue: []);
      final connection = OmiDeviceConnection(_testDevice(), transport);

      expect(() => connection.performGetAudioCodec(), throwsA(isA<StateError>()));
    });
  });
}
