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
}
