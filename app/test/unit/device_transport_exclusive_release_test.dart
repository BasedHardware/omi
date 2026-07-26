import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/devices/transports/device_transport.dart';

void main() {
  test('exclusive release runs even when the transport is already disconnected', () async {
    final transport = _ExclusiveFakeTransport();

    await releaseTransportForExclusiveOperation(transport);

    expect(transport.events, ['release native ownership', 'dispose Dart transport']);
  });

  test('release failure still disposes and remains the authoritative error', () async {
    final releaseError = StateError('unmanage failed');
    final transport = _ExclusiveFakeTransport()
      ..releaseError = releaseError
      ..disposeError = StateError('dispose failed');

    await expectLater(
      releaseTransportForExclusiveOperation(transport),
      throwsA(same(releaseError)),
    );

    expect(transport.events, ['release native ownership', 'dispose Dart transport']);
  });
}

class _ExclusiveFakeTransport extends DeviceTransport implements ExclusiveOperationTransport {
  final events = <String>[];
  Object? releaseError;
  Object? disposeError;

  @override
  String get deviceId => 'exclusive-fake';

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  Future<void> releaseForExclusiveOperation() async {
    events.add('release native ownership');
    final error = releaseError;
    if (error != null) throw error;
  }

  @override
  Future<void> dispose() async {
    events.add('dispose Dart transport');
    final error = disposeError;
    if (error != null) throw error;
  }

  @override
  Future<void> connect() async {}

  @override
  Future<void> disconnect() async {}

  @override
  Future<bool> isConnected() async => false;

  @override
  Future<bool> ping() async => false;

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) => const Stream.empty();

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async => const [];

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {}
}
