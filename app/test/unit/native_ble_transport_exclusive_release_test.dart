import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices/transports/native_ble_transport.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('exclusive release unmanages native intent after a transient disconnect', () async {
    const deviceId = 'exclusive-native-test';
    final hostApi = _FakeBleHostApi();
    final transport = NativeBleTransport(deviceId, hostApi: hostApi);
    addTearDown(transport.dispose);

    final connectFuture = transport.connect();
    await pumpEventQueue();
    BleBridge.instance.onDeviceReady(
      deviceId,
      [BleService(uuid: 'service', characteristicUuids: const [])],
    );
    await connectFuture;

    BleBridge.instance.onPeripheralDisconnected(deviceId, 'transient link loss');
    await pumpEventQueue();
    await transport.releaseForExclusiveOperation();

    expect(hostApi.events, ['manage:$deviceId', 'unmanage:$deviceId']);
  });

  test('transient disconnect retires old streams and reconnect exposes a fresh subscribed stream', () async {
    const deviceId = 'reconnect-stream-test';
    const serviceUuid = 'service';
    const characteristicUuid = 'audio';
    final hostApi = _FakeBleHostApi();
    final transport = NativeBleTransport(deviceId, hostApi: hostApi);

    final connectFuture = transport.connect();
    await pumpEventQueue();
    BleBridge.instance.onDeviceReady(
      deviceId,
      [
        BleService(
          uuid: serviceUuid,
          characteristicUuids: const [characteristicUuid],
        ),
      ],
    );
    await connectFuture;

    final oldValues = <List<int>>[];
    final oldStreamDone = Completer<void>();
    transport.getCharacteristicStream(serviceUuid, characteristicUuid).listen(
          oldValues.add,
          onDone: oldStreamDone.complete,
        );

    BleBridge.instance.onPeripheralDisconnected(deviceId, 'transient link loss');
    await oldStreamDone.future;
    BleBridge.instance.onDeviceReady(
      deviceId,
      [
        BleService(
          uuid: serviceUuid,
          characteristicUuids: const [characteristicUuid],
        ),
      ],
    );
    await pumpEventQueue();

    final newValues = <List<int>>[];
    final newStreamDone = Completer<void>();
    transport.getCharacteristicStream(serviceUuid, characteristicUuid).listen(
          newValues.add,
          onDone: newStreamDone.complete,
        );
    BleBridge.instance.onCharacteristicValueUpdated(
      deviceId,
      serviceUuid,
      characteristicUuid,
      Uint8List.fromList([1, 2, 3]),
    );
    await pumpEventQueue();

    expect(oldValues, isEmpty);
    expect(newValues, [
      [1, 2, 3],
    ]);
    expect(
      hostApi.events.where((event) => event.startsWith('subscribe:')),
      hasLength(2),
    );

    await transport.dispose();
    await newStreamDone.future;
  });
}

class _FakeBleHostApi extends BleHostApi {
  final events = <String>[];

  @override
  Future<void> manageDevice(String uuid, bool requiresBond) async {
    events.add('manage:$uuid');
  }

  @override
  Future<void> unmanageDevice(String uuid) async {
    events.add('unmanage:$uuid');
  }

  @override
  Future<void> subscribeCharacteristic(
    String peripheralUuid,
    String serviceUuid,
    String characteristicUuid,
  ) async {
    events.add('subscribe:$peripheralUuid:$serviceUuid:$characteristicUuid');
  }
}
