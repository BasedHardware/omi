import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class _FakeTransport extends DeviceTransport {
  final StreamController<List<int>> notifications = StreamController<List<int>>.broadcast();
  final StreamController<DeviceTransportState> states = StreamController<DeviceTransportState>.broadcast();
  List<int>? response;
  int writeCount = 0;

  @override
  String get deviceId => 'cv1';

  @override
  Future<void> connect() async {}

  @override
  Future<void> disconnect() async {}

  @override
  Future<void> dispose() async {
    await notifications.close();
    await states.close();
  }

  @override
  Stream<DeviceTransportState> get connectionStateStream => states.stream;

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) => notifications.stream;

  @override
  Future<bool> isConnected() async => true;

  @override
  Future<bool> ping() async => true;

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async => [];

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    writeCount++;
    final value = response;
    if (value != null) notifications.add(value);
  }
}

BtDevice _device() => BtDevice(name: 'Omi', id: 'cv1', type: DeviceType.omi, rssi: -40);

void main() {
  test('ring-info STORAGE_NOT_READY ACK fails immediately with its typed status', () async {
    final transport = _FakeTransport()..response = [RingProtocol.notifyAck, RingProtocol.statusStorageNotReady];
    final connection = OmiDeviceConnection(_device(), transport);

    await expectLater(
      connection.performGetRingInfo(),
      throwsA(
        isA<RingCommandRejectedException>()
            .having((error) => error.status, 'status', RingProtocol.statusStorageNotReady)
            .having((error) => error.isRetryable, 'retryable', isTrue),
      ),
    );
    expect(transport.writeCount, 1);
    await transport.dispose();
  });

  test('ring-info retry is bounded and succeeds after a transient not-ready response', () async {
    var attempts = 0;
    final delays = <Duration>[];
    final expected = RingInfo(readSeq: 4, writeSeq: 9, capacityPackets: 100, droppedPackets: 0, packetSize: 444);
    const policy = RingInfoRetryPolicy(maxAttempts: 3);

    final result = await policy.run(
      () async {
        attempts++;
        if (attempts == 1) {
          throw const RingCommandRejectedException(
            command: 'ring info',
            status: RingProtocol.statusStorageNotReady,
          );
        }
        return expected;
      },
      wait: (delay) async => delays.add(delay),
    );

    expect(result, same(expected));
    expect(attempts, 2);
    expect(delays, [const Duration(milliseconds: 500)]);
  });

  test('ring-info retry stops after the configured attempt budget', () async {
    var attempts = 0;
    const policy = RingInfoRetryPolicy(maxAttempts: 3, backoff: [Duration.zero]);

    await expectLater(
      policy.run(
        () async {
          attempts++;
          throw const RingCommandRejectedException(
            command: 'ring info',
            status: RingProtocol.statusStorageNotReady,
          );
        },
        wait: (_) async {},
      ),
      throwsA(isA<RingCommandRejectedException>()),
    );

    expect(attempts, 3);
  });
}
