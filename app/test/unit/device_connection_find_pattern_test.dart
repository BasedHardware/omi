import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class _RecordingTransport extends DeviceTransport {
  final List<(String, String, List<int>)> writes = [];
  int writeAttempts = 0;
  int? failOnAttempt;
  bool connected = true;
  Completer<void>? writeBlocker;

  @override
  String get deviceId => 'omi-1';

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
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async => [];

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    writeAttempts++;
    await writeBlocker?.future;
    if (writeAttempts == failOnAttempt) throw StateError('write failed');
    writes.add((serviceUuid, characteristicUuid, List<int>.from(data)));
  }

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  Future<void> dispose() async {}
}

OmiDeviceConnection _connection(_RecordingTransport transport) =>
    OmiDeviceConnection(BtDevice(id: transport.deviceId, name: 'Omi', type: DeviceType.omi, rssi: -40), transport);

void main() {
  test('find-device pattern sends three distinct long haptic pulses', () {
    fakeAsync((async) {
      final transport = _RecordingTransport();
      bool? result;

      _connection(transport).playFindDevicePattern().then((value) => result = value);
      async.flushMicrotasks();

      expect(transport.writes, hasLength(1));
      expect(transport.writes.single.$1, speakerDataStreamServiceUuid);
      expect(transport.writes.single.$2, speakerDataStreamCharacteristicUuid);
      expect(transport.writes.single.$3, [3]);

      async.elapse(const Duration(milliseconds: 750));
      async.flushMicrotasks();
      expect(transport.writes, hasLength(2));

      async.elapse(const Duration(milliseconds: 750));
      async.flushMicrotasks();

      expect(result, isTrue);
      expect(transport.writes, hasLength(3));
      for (final write in transport.writes) {
        expect(write.$1, speakerDataStreamServiceUuid);
        expect(write.$2, speakerDataStreamCharacteristicUuid);
        expect(write.$3, [3]);
      }
    });
  });

  test('find-device pattern stops and reports failure when a pulse cannot be sent', () {
    fakeAsync((async) {
      final transport = _RecordingTransport()..failOnAttempt = 2;
      bool? result;

      _connection(transport).playFindDevicePattern().then((value) => result = value);
      async.flushMicrotasks();
      async.elapse(const Duration(milliseconds: 750));
      async.flushMicrotasks();

      expect(result, isFalse);
      expect(transport.writeAttempts, 2);
      expect(transport.writes, hasLength(1));

      async.elapse(const Duration(seconds: 2));
      expect(transport.writeAttempts, 2);
    });
  });

  test('find-device pattern reports failure without writing when disconnected', () {
    fakeAsync((async) {
      final transport = _RecordingTransport()..connected = false;
      bool? result;

      _connection(transport).playFindDevicePattern().then((value) => result = value);
      async.flushMicrotasks();

      expect(result, isFalse);
      expect(transport.writeAttempts, 0);
      expect(transport.writes, isEmpty);
    });
  });

  test('find-device pattern times out a stalled haptic write', () {
    fakeAsync((async) {
      final blocker = Completer<void>();
      final transport = _RecordingTransport()..writeBlocker = blocker;
      bool? result;

      _connection(transport).playFindDevicePattern().then((value) => result = value);
      async.flushMicrotasks();
      expect(transport.writeAttempts, 1);

      async.elapse(const Duration(seconds: 5));
      async.flushMicrotasks();

      expect(result, isFalse);
      expect(transport.writeAttempts, 1);
      expect(transport.writes, isEmpty);

      blocker.complete();
      async.flushMicrotasks();
      expect(transport.writeAttempts, 1);
    });
  });
}
