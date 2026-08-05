import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/limitless_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class FakeDeviceTransport extends DeviceTransport {
  final Map<String, StreamController<List<int>>> _rxControllers = {};
  final StreamController<DeviceTransportState> _stateController = StreamController<DeviceTransportState>.broadcast();
  final List<List<int>> writes = [];

  StreamController<List<int>> _controllerFor(String characteristicUuid) {
    return _rxControllers.putIfAbsent(characteristicUuid, () => StreamController<List<int>>.broadcast());
  }

  void emit(String characteristicUuid, List<int> data) {
    _controllerFor(characteristicUuid).add(data);
  }

  @override
  String get deviceId => 'fake-limitless';

  @override
  Future<void> connect() async {}

  @override
  Future<void> disconnect() async {}

  @override
  Future<bool> isConnected() async => true;

  @override
  Future<bool> ping() async => true;

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) {
    return _controllerFor(characteristicUuid).stream;
  }

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async => [];

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    writes.add(List<int>.from(data));
  }

  @override
  Stream<DeviceTransportState> get connectionStateStream => _stateController.stream;

  @override
  Future<void> dispose() async {}
}

List<int> varint(int value) {
  final out = <int>[];
  var v = value;
  while (v > 0x7f) {
    out.add((v & 0x7f) | 0x80);
    v >>= 7;
  }
  out.add(v & 0x7f);
  return out;
}

List<int> intField(int fieldNum, int value) => [...varint((fieldNum << 3) | 0), ...varint(value)];

List<int> bytesField(int fieldNum, List<int> data) => [...varint((fieldNum << 3) | 2), ...varint(data.length), ...data];

List<int> bleWrapper(int index, int seq, int numFrags, List<int> payload) => [
  ...intField(1, index),
  ...intField(2, seq),
  ...intField(3, numFrags),
  ...bytesField(4, payload),
];

/// Type-8 RX: f8 → f6 EPOCH_MS (varint), as described in #5734.
List<int> type8ClockPacket({required int index, required int epochMs}) =>
    bleWrapper(index, 0, 1, bytesField(8, intField(6, epochMs)));

/// Type-8 RX alternate: f8 → f6 length-delimited → f1 EPOCH_MS (SetCurrentTime mirror).
List<int> type8ClockPacketNested({required int index, required int epochMs}) =>
    bleWrapper(index, 0, 1, bytesField(8, bytesField(6, intField(1, epochMs))));

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Type-8 pendant clock parse', () {
    test('extracts epoch from f8→f6 varint', () {
      const epoch = 1750000005000;
      final payload = bytesField(8, intField(6, epoch));
      expect(LimitlessDeviceConnection.extractType8PendantEpochMs(payload), epoch);
    });

    test('extracts epoch from f8→f6→f1 nested', () {
      const epoch = 1750000005000;
      final payload = bytesField(8, bytesField(6, intField(1, epoch)));
      expect(LimitlessDeviceConnection.extractType8PendantEpochMs(payload), epoch);
    });

    test('returns null when field 8 is absent', () {
      final payload = bytesField(2, intField(1, 42));
      expect(LimitlessDeviceConnection.extractType8PendantEpochMs(payload), isNull);
    });

    test('flash-page correction subtracts measured drift', () {
      // Pendant RTC was 5 minutes ahead of phone when measured.
      const driftOffsetMs = 5 * 60 * 1000;
      const rawTimestampMs = 1750000000000;
      final corrected = rawTimestampMs - driftOffsetMs;
      expect(corrected, rawTimestampMs - driftOffsetMs);
      expect(corrected, lessThan(rawTimestampMs));
    });
  });

  group('connect-time drift capture', () {
    test('Type-8 before SetCurrentTime sets clockDriftOffsetMs', () async {
      final transport = FakeDeviceTransport();
      final device = BtDevice(name: 'Limitless Pendant', id: 'fake-limitless', type: DeviceType.limitless, rssi: -50);
      final connection = LimitlessDeviceConnection(device, transport);

      const pendantAheadMs = 180000; // 3 minutes
      final connectFuture = connection.connect();

      // RX attaches after the first 1s delay inside connect().
      await Future.delayed(const Duration(milliseconds: 1100));
      final phoneBefore = DateTime.now().millisecondsSinceEpoch;
      final pendantEpoch = phoneBefore + pendantAheadMs;
      transport.emit(limitlessRxCharUuid, type8ClockPacket(index: 1, epochMs: pendantEpoch));
      await Future.delayed(const Duration(milliseconds: 50));

      await connectFuture;

      expect(connection.clockDriftOffsetMs, isNotNull);
      // Allow a few seconds of wall-clock skew from connect delays.
      expect(connection.clockDriftOffsetMs!, closeTo(pendantAheadMs, 5000));

      await connection.disconnect();
    });

    test('Type-8 after SetCurrentTime does not overwrite drift', () async {
      final transport = FakeDeviceTransport();
      final device = BtDevice(name: 'Limitless Pendant', id: 'fake-limitless', type: DeviceType.limitless, rssi: -50);
      final connection = LimitlessDeviceConnection(device, transport);

      const firstDriftMs = 120000;
      final connectFuture = connection.connect();
      await Future.delayed(const Duration(milliseconds: 1100));
      final phoneBefore = DateTime.now().millisecondsSinceEpoch;
      transport.emit(limitlessRxCharUuid, type8ClockPacket(index: 1, epochMs: phoneBefore + firstDriftMs));
      await connectFuture;

      final captured = connection.clockDriftOffsetMs;
      expect(captured, isNotNull);

      // Post-sync Type-8 would report ~0 drift; must not clobber the offline correction.
      transport.emit(limitlessRxCharUuid, type8ClockPacket(index: 2, epochMs: DateTime.now().millisecondsSinceEpoch));
      await Future.delayed(const Duration(milliseconds: 50));
      expect(connection.clockDriftOffsetMs, captured);

      await connection.disconnect();
    });
  });
}
