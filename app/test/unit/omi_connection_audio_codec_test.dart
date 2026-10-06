import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class _CodecTransport extends DeviceTransport {
  final List<List<int> Function()> readResponses;
  int readCount = 0;
  bool connected = true;

  _CodecTransport(this.readResponses);

  @override
  String get deviceId => 'omi-test';

  @override
  Future<void> connect() async {}

  @override
  Future<void> disconnect() async {}

  @override
  Future<bool> isConnected() async => connected;

  @override
  Future<bool> ping() async => connected;

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) => const Stream.empty();

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    readCount++;
    if (readResponses.isEmpty) return [];
    final idx = (readCount - 1).clamp(0, readResponses.length - 1);
    return readResponses[idx]();
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {}

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  Future<void> dispose() async {}
}

OmiDeviceConnection _connection(_CodecTransport transport) =>
    OmiDeviceConnection(BtDevice(id: transport.deviceId, name: 'Omi', type: DeviceType.omi, rssi: -40), transport);

void main() {
  group('OmiDeviceConnection audio codec detection', () {
    test('codec 20 resolves to opus', () async {
      final transport = _CodecTransport([() => [20]]);
      final conn = _connection(transport);

      final codec = await conn.performGetAudioCodec();
      expect(codec, BleAudioCodec.opus);
      expect(transport.readCount, 1);
    });

    test('codec 21 resolves to opusFS320', () async {
      final transport = _CodecTransport([() => [21]]);
      final conn = _connection(transport);

      final codec = await conn.performGetAudioCodec();
      expect(codec, BleAudioCodec.opusFS320);
      expect(transport.readCount, 1);
    });

    test('codec 1 resolves to pcm8 only for explicit value 1', () async {
      final transport = _CodecTransport([() => [1]]);
      final conn = _connection(transport);

      final codec = await conn.performGetAudioCodec();
      expect(codec, BleAudioCodec.pcm8);
      expect(transport.readCount, 1);
    });

    test('unknown codec id resolves to unknown, never pcm8', () async {
      final transport = _CodecTransport([() => [99]]);
      final conn = _connection(transport);

      final codec = await conn.performGetAudioCodec();
      expect(codec, BleAudioCodec.unknown);
    });

    test('transient read error retries and resolves on subsequent attempt', () async {
      final transport = _CodecTransport([
        () => throw StateError('GATT peripheral busy'),
        () => [],
        () => [20],
      ]);
      final conn = _connection(transport);

      final codec = await conn.performGetAudioCodec();
      expect(codec, BleAudioCodec.opus);
      expect(transport.readCount, 3);
    });

    test('persistent read failure returns unknown and never defaults to pcm8', () async {
      final transport = _CodecTransport([
        () => throw StateError('GATT error'),
        () => throw StateError('GATT error'),
        () => throw StateError('GATT error'),
      ]);
      final conn = _connection(transport);

      final codec = await conn.performGetAudioCodec();
      expect(codec, BleAudioCodec.unknown);
      expect(codec, isNot(BleAudioCodec.pcm8));
    });

    test('persistent empty read returns unknown and never defaults to pcm8', () async {
      final transport = _CodecTransport([
        () => [],
        () => [],
        () => [],
      ]);
      final conn = _connection(transport);

      final codec = await conn.performGetAudioCodec();
      expect(codec, BleAudioCodec.unknown);
      expect(codec, isNot(BleAudioCodec.pcm8));
    });

    test('subsequent transient failure falls back to cached codec', () async {
      final transport = _CodecTransport([
        () => [20],
        () => throw StateError('GATT timeout'),
        () => throw StateError('GATT timeout'),
        () => throw StateError('GATT timeout'),
      ]);
      final conn = _connection(transport);

      final firstCodec = await conn.getAudioCodec();
      expect(firstCodec, BleAudioCodec.opus);

      final secondCodec = await conn.getAudioCodec();
      expect(secondCodec, BleAudioCodec.opus);
    });
  });
}
