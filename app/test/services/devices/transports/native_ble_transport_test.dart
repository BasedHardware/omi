import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices/transports/native_ble_transport.dart';

const _deviceId = 'omi-test-device';
const _serviceUuid = '23ba7924-0000-1000-7450-346eac492e92';
const _characteristicUuid = '23ba7925-0000-1000-7450-346eac492e92';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final hostApiChannelNames = <String>{};

  void setHostApiHandler(String methodName, Future<Object?> Function(Object? message) handler) {
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    final channelName = 'dev.flutter.pigeon.omi_pigeon.BleHostApi.$methodName';
    hostApiChannelNames.add(channelName);
    messenger.setMockMessageHandler(channelName, (ByteData? message) async {
      final decoded = BleHostApi.pigeonChannelCodec.decodeMessage(message);
      final response = await handler(decoded);
      return BleHostApi.pigeonChannelCodec.encodeMessage(response);
    });
  }

  tearDown(() {
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    for (final channelName in hostApiChannelNames) {
      messenger.setMockMessageHandler(channelName, null);
    }
    hostApiChannelNames.clear();
  });

  for (final error in ['gatt_status_22', 'pairing_lost']) {
    test('disconnect before readiness propagates $error without changing its cause', () async {
      var pairingLostNotifications = 0;
      BleBridge.instance.pairingLostCallback = () => pairingLostNotifications++;
      addTearDown(() => BleBridge.instance.pairingLostCallback = null);
      setHostApiHandler('getBluetoothState', (message) async => ['on']);
      setHostApiHandler('manageDevice', (message) async {
        BleBridge.instance.onPeripheralDisconnected(_deviceId, error);
        return <Object?>[];
      });

      final transport = NativeBleTransport(_deviceId);
      addTearDown(transport.dispose);

      await expectLater(transport.connect(), throwsA(error));
      expect(pairingLostNotifications, error == 'pairing_lost' ? 1 : 0);
    });
  }

  test('keeps button listener alive and resubscribes after reconnect', () async {
    final subscribeCalls = <List<Object?>>[];
    final services = [
      BleService(
        uuid: _serviceUuid,
        characteristicUuids: [_characteristicUuid],
      ),
    ];

    setHostApiHandler('manageDevice', (message) async {
      BleBridge.instance.onDeviceReady(_deviceId, services);
      return <Object?>[];
    });
    setHostApiHandler('subscribeCharacteristic', (message) async {
      subscribeCalls.add((message! as List<Object?>).toList());
      return <Object?>[];
    });
    // NativeBleTransport.connect() gates on BluetoothReadiness.instance, which
    // queries the native adapter state through the pigeon BleHostApi channel.
    // The reply must be a List (pigeon wraps the scalar return value).
    setHostApiHandler('getBluetoothState', (message) async => ['on']);

    final transport = NativeBleTransport(_deviceId);
    addTearDown(transport.dispose);

    await transport.connect();
    final received = <List<int>>[];
    final subscription = transport.getCharacteristicStream(_serviceUuid, _characteristicUuid).listen(received.add);
    addTearDown(subscription.cancel);

    await Future<void>.delayed(Duration.zero);
    BleBridge.instance.onCharacteristicValueUpdated(
      _deviceId,
      _serviceUuid,
      _characteristicUuid,
      Uint8List.fromList([2, 0, 0, 0]),
    );
    await Future<void>.delayed(Duration.zero);

    BleBridge.instance.onPeripheralDisconnected(_deviceId, 'gatt_status_133');
    BleBridge.instance.onDeviceReady(_deviceId, services);
    await Future<void>.delayed(Duration.zero);
    BleBridge.instance.onCharacteristicValueUpdated(
      _deviceId,
      _serviceUuid,
      _characteristicUuid,
      Uint8List.fromList([2, 0, 0, 0]),
    );
    await Future<void>.delayed(Duration.zero);

    expect(subscribeCalls, hasLength(2));
    expect(received, [
      [2, 0, 0, 0],
      [2, 0, 0, 0],
    ]);
  });
  test('reading a characteristic the firmware does not expose skips the native read', () async {
    const disServiceUuid = '0000180a-0000-1000-8000-00805f9b34fb';
    const firmwareRevisionUuid = '00002a26-0000-1000-8000-00805f9b34fb';
    const serialNumberUuid = '00002a25-0000-1000-8000-00805f9b34fb';
    final readCalls = <List<Object?>>[];
    final services = [
      BleService(uuid: disServiceUuid, characteristicUuids: [firmwareRevisionUuid]),
    ];

    setHostApiHandler('manageDevice', (message) async {
      BleBridge.instance.onDeviceReady(_deviceId, services);
      return <Object?>[];
    });
    setHostApiHandler('getBluetoothState', (message) async => ['on']);
    setHostApiHandler('readCharacteristic', (message) async {
      readCalls.add((message! as List<Object?>).toList());
      return [Uint8List.fromList('3.0.21'.codeUnits)];
    });

    final transport = NativeBleTransport(_deviceId);
    addTearDown(transport.dispose);
    await transport.connect();

    expect(await transport.readCharacteristic(disServiceUuid, serialNumberUuid), isEmpty);
    expect(readCalls, isEmpty);

    expect(await transport.readCharacteristic(disServiceUuid, firmwareRevisionUuid), '3.0.21'.codeUnits);
    expect(readCalls, hasLength(1));
  });
}
