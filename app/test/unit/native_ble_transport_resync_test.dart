import 'dart:typed_data';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/services/devices/transports/native_ble_transport.dart';

class _FakeBleHostApi extends BleHostApi {
  final List<String> subscribed = [];

  @override
  Future<void> manageDevice(String uuid, bool requiresBond) async {}

  @override
  Future<void> subscribeCharacteristic(String peripheralUuid, String serviceUuid, String characteristicUuid) async {
    subscribed.add('$serviceUuid:$characteristicUuid');
  }

  @override
  Future<void> unsubscribeCharacteristic(String peripheralUuid, String serviceUuid, String characteristicUuid) async {}
}

void main() {
  const uuid = 'AA:BB:CC:DD:EE:FF';
  const serviceUuid = '19b10000-e8f2-537e-4f6c-d104768a1214';
  const charUuid = '19b10001-e8f2-537e-4f6c-d104768a1214';

  final services = [
    BleService(uuid: serviceUuid, characteristicUuids: [charUuid]),
  ];

  late NativeBleTransport transport;

  setUp(() {
    transport = NativeBleTransport(uuid, hostApi: _FakeBleHostApi());
  });

  tearDown(() async {
    await transport.dispose();
  });

  test('a repeated device-ready for a live link keeps existing subscribers streaming', () async {
    BleBridge.instance.onDeviceReady(uuid, services);
    transport.getCharacteristicStream(serviceUuid, charUuid).listen((_) {});

    BleBridge.instance.onPeripheralDisconnected(uuid, null);
    BleBridge.instance.onDeviceReady(uuid, services);

    final received = <List<int>>[];
    final subscription = transport.getCharacteristicStream(serviceUuid, charUuid).listen(received.add);
    addTearDown(subscription.cancel);

    // Native re-emits ready when Dart asks to connect a link that is already up.
    BleBridge.instance.onDeviceReady(uuid, services);
    BleBridge.instance.onCharacteristicValueUpdated(uuid, serviceUuid, charUuid, Uint8List.fromList([1, 2, 3]));
    await Future<void>.delayed(Duration.zero);

    expect(received, [
      [1, 2, 3],
    ]);
  });

  test('device-ready after a disconnect restores the transport to connected', () async {
    BleBridge.instance.onDeviceReady(uuid, services);

    final states = <DeviceTransportState>[];
    final subscription = transport.connectionStateStream.listen(states.add);
    addTearDown(subscription.cancel);

    BleBridge.instance.onPeripheralDisconnected(uuid, null);
    BleBridge.instance.onDeviceReady(uuid, services);
    await Future<void>.delayed(Duration.zero);

    expect(states, [DeviceTransportState.disconnected, DeviceTransportState.connected]);
  });

  test('isBleAudioCharacteristicUuid covers wearable audio notify chars', () {
    expect(isBleAudioCharacteristicUuid(audioDataStreamCharacteristicUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(friendPendantAudioCharacteristicUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(limitlessRxCharUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(beeAudioCharacteristicUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(fieldyAudioCharacteristicUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(plaudNotifyCharUuid), isTrue);
    expect(isBleAudioCharacteristicUuid(batteryLevelCharacteristicUuid), isFalse);
    expect(isBleAudioCharacteristicUuid(plaudWriteCharUuid), isFalse);
  });

  test('after reconnect, silent audio CCCD is retried once then left dead', () {
    fakeAsync((async) {
      transport.dispose();
      final hostApi = _FakeBleHostApi();
      transport = NativeBleTransport(uuid, hostApi: hostApi);

      const audioChar = '19b10001-e8f2-537e-4f6c-d104768a1214';
      final audioServices = [
        BleService(uuid: serviceUuid, characteristicUuids: [audioChar]),
      ];

      BleBridge.instance.onDeviceReady(uuid, audioServices);
      transport.getCharacteristicStream(serviceUuid, audioChar).listen((_) {});
      async.flushMicrotasks();

      BleBridge.instance.onPeripheralDisconnected(uuid, null);
      BleBridge.instance.onDeviceReady(uuid, audioServices);
      async.flushMicrotasks();

      final subscribesBeforeWatch = hostApi.subscribed.where((s) => s.contains(audioChar)).length;
      expect(subscribesBeforeWatch, greaterThanOrEqualTo(1));

      async.elapse(const Duration(seconds: 4));
      async.flushMicrotasks();
      final afterFirstSilence = hostApi.subscribed.where((s) => s.contains(audioChar)).length;
      expect(afterFirstSilence, subscribesBeforeWatch + 1, reason: 'one CCCD resubscribe on silence');

      async.elapse(const Duration(seconds: 4));
      async.flushMicrotasks();
      expect(
        hostApi.subscribed.where((s) => s.contains(audioChar)).length,
        afterFirstSilence,
        reason: 'do not tight-loop resubscribe after the single retry',
      );
    });
  });

  test('Bee audio UUID silence after reconnect still schedules one CCCD retry', () {
    fakeAsync((async) {
      transport.dispose();
      final hostApi = _FakeBleHostApi();
      transport = NativeBleTransport(uuid, hostApi: hostApi);

      final audioServices = [
        BleService(uuid: beeServiceUuid, characteristicUuids: [beeAudioCharacteristicUuid]),
      ];

      BleBridge.instance.onDeviceReady(uuid, audioServices);
      transport.getCharacteristicStream(beeServiceUuid, beeAudioCharacteristicUuid).listen((_) {});
      async.flushMicrotasks();

      BleBridge.instance.onPeripheralDisconnected(uuid, null);
      BleBridge.instance.onDeviceReady(uuid, audioServices);
      async.flushMicrotasks();

      final subscribesBeforeWatch =
          hostApi.subscribed.where((s) => s.toLowerCase().contains(beeAudioCharacteristicUuid.toLowerCase())).length;
      expect(subscribesBeforeWatch, greaterThanOrEqualTo(1));

      async.elapse(const Duration(seconds: 4));
      async.flushMicrotasks();
      expect(
        hostApi.subscribed.where((s) => s.toLowerCase().contains(beeAudioCharacteristicUuid.toLowerCase())).length,
        subscribesBeforeWatch + 1,
        reason: 'Bee audio UUID must be recognized so CCCD retry arms',
      );
    });
  });
}
